import os
import time
import math
import ahtx0
import utime
import cmath
import update
import network
import machine
import urequests
from hx711 import HX711
from machine import Timer
from bmp280 import BMP280
from machine import I2S, Pin, I2C, ADC
from urllib_parse import parse_qs  # Váš vlastní modul pro parsování query stringu
import socket  # Potřebný pro režim konfigurace

# Název souboru s konfigurací
CONFIG_FILE = "config.txt"

# Funkce pro načtení konfigurace ze souboru
def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            lines = f.readlines()
        config = {}
        for line in lines:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key] = value
        return config
    except OSError:
        return None

# Funkce pro kontrolu, zda chceme spustit konfigurační režim
def force_config_mode():
    # Využíváme vestavěné tlačítko "boot" (GPIO0) k vynucení konfigurace.
    # Tlačítko reset nelze použít, jelikož resetuje zařízení.
    boot_button = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
    if boot_button.value() == 0:
        print("Boot button stisknuto, spuštění konfiguračního režimu.")
        return True
    return False

# Režim konfigurace: Spustí se AP mód a jednoduchý webový server, kde zadáte potřebné údaje
def run_config_mode():
    print("Spouštím konfigurační režim. Připojte se k WiFi AP s názvem 'Včely_nastavení'.")
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Včely_nastavení", authmode=3, password="12345678")
    ip = ap.ifconfig()[0]
    print("AP spuštěn, IP adresa:", ip)
    
    html = """<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <title>ESP32 Konfigurace</title>
  </head>
  <body>
    <h1>Nastavení ESP32</h1>
    <form method="POST">
      <label>WiFi SSID:</label><br>
      <input type="text" name="ssid"><br><br>
      <label>WiFi Heslo:</label><br>
      <input type="password" name="wifi_password"><br><br>
      <label>ThingSpeak API klíč:</label><br>
      <input type="text" name="thingspeak_api"><br><br>
      <label>CallMeBot API klíč:</label><br>
      <input type="text" name="callmebot_api"><br><br>
      <label>Telefonní číslo:</label><br>
      <input type="text" name="phone"><br><br>
      <input type="submit" value="Uložit">
    </form>
  </body>
</html>
"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(1)
    print("Server běží na portu 80")
    
    while True:
        cl, addr = s.accept()
        print("Připojeno:", addr)
        cl_file = cl.makefile("rwb", 0)
        request_line = cl_file.readline()
        if not request_line:
            cl.close()
            continue
        try:
            method, path, protocol = request_line.decode().split()
        except Exception as e:
            cl.close()
            continue
        
        if method == "POST":
            content_length = 0
            while True:
                header = cl_file.readline().decode().strip()
                if header == "":
                    break
                if header.lower().startswith("content-length"):
                    content_length = int(header.split(":")[1].strip())
            post_data = cl_file.read(content_length).decode()
            print("Přijatá data:", post_data)
            params = parse_qs(post_data)
            # Uložení zadaných hodnot do konfiguračního souboru
            config_data = "ssid=" + params.get("ssid", "") + "\n"
            config_data += "wifi_password=" + params.get("wifi_password", "") + "\n"
            config_data += "thingspeak_api=" + params.get("thingspeak_api", "") + "\n"
            config_data += "callmebot_api=" + params.get("callmebot_api", "") + "\n"
            config_data += "phone=" + params.get("phone", "") + "\n"
            with open(CONFIG_FILE, "w") as f:
                f.write(config_data)
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n<h1>Konfigurace uložena! Zařízení se restartuje.</h1>"
            cl.send(response)
            cl.close()
            s.close()
            time.sleep(2)
            machine.reset()
        else:
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + html
            cl.send(response)
            cl.close()

# Pokud je tlačítko boot stisknuto, nebo konfigurační soubor neexistuje, spustí se konfigurační režim
if force_config_mode():
    run_config_mode()

config = load_config()
if config is None:
    run_config_mode()

# Nastavení parametrů z konfiguračního souboru (výchozí hodnoty se použijí, pokud něco chybí)
WIFI_SSID = config.get("ssid", "Podhura 2")
WIFI_PASSWORD = config.get("wifi_password", "truDy659")
THINGSPEAK_API_KEY = config.get("thingspeak_api", "OW890QF6K2CTV5P6")
CALLMEBOT_API = config.get("callmebot_api", "")
PHONE = config.get("phone", "")

# Funkce pro připojení k WiFi pomocí načtených údajů
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    while not wlan.isconnected():
        time.sleep(1)
    print("Připojeno k WiFi:", wlan.ifconfig())

# Nastavení ADC
adc = machine.ADC(machine.Pin(32))
adc.atten(machine.ADC.ATTN_11DB)
FS = 16000  # Vzorkovací frekvence
N = 256     # Počet vzorků

# Nastavení I2C sběrnice pro AHT20 a BMP280
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = ahtx0.AHT20(i2c)
bmp = BMP280(i2c, address=0x77)
print("I2C zařízení:", i2c.scan())

# Nastavení HX711 pro vážení
DT = 4   # Data pin
SCK = 5  # Clock pin
hx = HX711(d_out=DT, pd_sck=SCK)
hx.tare()
CALIBRATION_FACTOR = 27500
hx.set_scale(CALIBRATION_FACTOR)

# ThingSpeak URL
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# Funkce pro uložení a načtení první váhy (tary)
def save_first_weight(first_weight):
    with open("first_weight.txt", "w") as file:
        file.write(str(first_weight))
    print(f"Tara {first_weight} uložena do souboru.")

def load_first_weight():
    try:
        with open("first_weight.txt", "r") as file:
            first_weight = float(file.read())
        print(f"Načtena tara: {first_weight}")
        return first_weight
    except (OSError, ValueError):
        print("Tara nenalezena nebo poškozena.")
        return None

# Funkce pro odeslání dat na ThingSpeak
def send_data(temperature_aht, humidity_aht, temperature_bmp, pressure_bmp, weight, rssi, prum_frekvence):
    url = (f"{THINGSPEAK_URL}?api_key={THINGSPEAK_API_KEY}"
           f"&field1={temperature_aht}"
           f"&field2={humidity_aht}"
           f"&field3={temperature_bmp}"
           f"&field4={pressure_bmp}"
           f"&field5={weight}"
           f"&field6={rssi}"
           f"&field7={prum_frekvence}"
           )
    try:
        response = urequests.get(url)
        print("Odpověď serveru:", response.text)
        response.close()
    except Exception as e:
        print("Chyba při odesílání dat:", e)

# Funkce pro měření dat ze senzorů
def wheather_sensor_measure():
    temperature_aht = sensor.temperature - 1.5
    humidity_aht = sensor.relative_humidity
    print("AHT senzor:")
    print(f"Teplota: {temperature_aht:.2f} °C, Vlhkost: {humidity_aht:.2f} %")
    temperature_bmp, pressure_bmp = bmp.read_temperature_pressure()
    print("BMP senzor:")
    print(f"Teplota: {temperature_bmp:.2f} °C, Tlak: {pressure_bmp:.2f} hPa")
    return temperature_aht, humidity_aht, temperature_bmp, pressure_bmp

# Funkce pro měření váhy
def read_weight():
    value = hx.read_average(10)
    weight = (value - tare_value) / CALIBRATION_FACTOR
    print(f"Váha: {weight} kg")
    return weight

# Funkce pro odebrání vzorků a odstranění DC složky
def get_samples():
    samples = []
    for _ in range(N):
        samples.append(adc.read())
        utime.sleep_us(int(1e6 / FS))
    mean_value = sum(samples) / len(samples)
    samples = [s - mean_value for s in samples]
    return samples

# Rekurzivní FFT (rychlá Fourierova transformace)
def fft(signal):
    N = len(signal)
    if N <= 1:
        return signal
    even = fft(signal[0::2])
    odd = fft(signal[1::2])
    T = [cmath.exp(-2j * math.pi * k / N) * odd[k] for k in range(N // 2)]
    return [even[k] + T[k] for k in range(N // 2)] + [even[k] - T[k] for k in range(N // 2)]

# Funkce pro určení dominantní frekvence
def measure_freq():
    samples = get_samples()
    spectrum = fft(samples)
    magnitudes = [abs(c) for c in spectrum[:N // 2]]
    peak_index = magnitudes.index(max(magnitudes))
    peak_freq = round(((peak_index * FS / N) / 2.05), 1)
    frekvence = peak_freq
    print(f"Dominantní frekvence: {frekvence} Hz")
    return frekvence

# Funkce pro odeslání zprávy přes CallMeBot (WhatsApp)
def send_whatsapp(number, api_key):
    message = "TEST+VČELY:+asi+si+balíme+baťůžky+a+mizíme+z+úlu!!!"
    url = f"https://api.callmebot.com/whatsapp.php?phone={number}&text={message}&apikey={api_key}"
    try:
        response = urequests.get(url)
        print("Odpověď WhatsApp API:", response.text)
        response.close()
    except Exception as e:
        print("Chyba při odesílání WhatsApp zprávy:", e)

# Funkce pro přechod do hlubokého spánku
def deep_sleep(seconds):
    print("Přecházím do hlubokého spánku.")
    machine.deepsleep(seconds)

# Hlavní program
connect_wifi()

# Inicializace instance pro aktualizaci a kontrola aktualizace souboru main.py
updater = update.Update("https://raw.githubusercontent.com/MartinMiso/aktualizace_2/refs/heads/main/main.py")
updater.compare_and_update("main.py")

# Načtení nebo nastavení první váhy (tary)
first_weight = load_first_weight()
if first_weight is None:
    tare_value = hx.read_average(10)
    save_first_weight(tare_value)
else:
    tare_value = first_weight
    print(f"Používám uloženou taru: {tare_value}")

while True:
    try:
        temp_aht, hum_aht, temp_bmp, pres_bmp = wheather_sensor_measure()
        weight = read_weight()
        wlan = network.WLAN(network.STA_IF)
        rssi = wlan.status('rssi') if wlan.isconnected() else None

        # Měření frekvence: odebere 35 měření a spočítá průměr
        prumer = []
        for _ in range(35):
            time.sleep(0.5)
            frekvence = measure_freq()
            prumer.append(frekvence)
        prum_frekvence = sum(prumer) / len(prumer)
        print(f"Průměrná frekvence: {prum_frekvence} Hz")

        # Pokud průměrná frekvence spadá do určitého intervalu, odešle WhatsApp upozornění
        if 350 < prum_frekvence < 500:
            send_whatsapp(PHONE, CALLMEBOT_API)
            print("Asi se rojíme")
        else:
            print("Vše OK")
        send_data(temp_aht, hum_aht, temp_bmp, pres_bmp, weight, rssi, prum_frekvence)
    except Exception as e:
        print("Chyba senzoru:", e)
     
    deep_sleep(600000)  # Hluboký spánek na 10 minut
