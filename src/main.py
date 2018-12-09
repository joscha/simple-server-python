from RPLCD.i2c import CharLCD
import solaredge
import os
import time
import requests
import sys
from datetime import datetime, timedelta
from suntime import Sun
from dateutil.tz import tzlocal


if __name__ == '__main__':
    lcd = CharLCD(i2c_expander='PCF8574', address=0x3f, port=1,
              cols=16, rows=2, dotsize=8,
              charmap='A02',
              auto_linebreaks=False,
              backlight_enabled=False)
    lcd.clear()
    lcd.write_string('...initializing')

    # characters via https://omerk.github.io/lcdchargen/
    bitmap_house = (
        0b00100,
        0b01110,
        0b11111,
        0b11111,
        0b11011,
        0b11011,
        0b11011,
        0b00000
    )
    lcd.create_char(0, bitmap_house)

    bitmap_solar_panels = (
        0b11011,
        0b11011,
        0b11011,
        0b00000,
        0b11011,
        0b11011,
        0b11011,
        0b00000
    )
    lcd.create_char(1, bitmap_solar_panels)

    bitmap_power_pole = (
        0b00100,
        0b01110,
        0b00100,
        0b01110,
        0b11111,
        0b00100,
        0b00100,
        0b00000
    )
    bitmap_power_plug = (
        0b01010,
        0b01010,
        0b11111,
        0b11111,
        0b11111,
        0b01110,
        0b00100,
        0b00000
    )
    lcd.create_char(2, bitmap_power_plug)

    # This *should* be \x7F but it seems as if the LED I am using
    # doesn't know this...
    bitmap_arrow_left = (
        0b00000,
        0b00100,
        0b01000,
        0b11111,
        0b01000,
        0b00100,
        0b00000,
        0b00000
    )
    lcd.create_char(3, bitmap_arrow_left)

    bitmap_loading = (
        0b00100,
        0b01000,
        0b11100,
        0b01000,
        0b00010,
        0b00111,
        0b00010,
        0b00100
    )
    lcd.create_char(4, bitmap_loading)
    

    pv_icon = '\x01'
    arrow_right_icon = '\x7E'
    house_icon = '\x00'
    arrow_left_icon = '\x03'
    grid_icon = '\x02'
    loading_icon = '\x04'

    if 'SOLAREDGE_API_KEY' in os.environ:
        SOLAREDGE_API_KEY = os.environ['SOLAREDGE_API_KEY']
    else:
        lcd.clear()
        lcd.write_string('SOLAREDGE_API_KEY missing')
        sys.exit(1)

    if 'SOLAREDGE_SITE_ID' in os.environ:
        SOLAREDGE_SITE_ID = os.environ['SOLAREDGE_SITE_ID']
    else:
        lcd.clear()
        lcd.write_string('SOLAREDGE_SITE_ID missing')
        sys.exit(1)

    s = solaredge.Solaredge(SOLAREDGE_API_KEY)

    # coordinates via https://www.latlong.net/
    if 'LONGITUDE' in os.environ:
        LONGITUDE = os.environ['LONGITUDE']
    else:
        lcd.clear()
        lcd.write_string('LONGITUDE missing')
        sys.exit(1)

    if 'LATITUDE' in os.environ:
        LATITUDE = os.environ['LATITUDE']
    else:
        lcd.clear()
        lcd.write_string('LATITUDE missing')
        sys.exit(1)

    sun = Sun(float(LATITUDE), float(LONGITUDE))

    lcd.clear()
    while True:
        try:
            now = datetime.now(tzlocal())
            # We get the day before today and then its sunrise, which is the sunrise leading up to now
            today_sr = sun.get_local_sunrise_time(datetime.today() - timedelta(1))
            today_ss = sun.get_local_sunset_time(datetime.today())
            lcd.backlight_enabled = now < today_sr or now > today_ss
            print(f"Backlight is enabled: {lcd.backlight_enabled}")
            lcd.home()
            lcd.write_string(loading_icon)
            print('loading data')
            currentPowerFlow = s.get_current_power_flow(SOLAREDGE_SITE_ID)["siteCurrentPowerFlow"]
            print(currentPowerFlow)
            grid_active = currentPowerFlow["GRID"]["status"].lower() == 'active'
            grid_kW = currentPowerFlow["GRID"]["currentPower"]

            load_active = currentPowerFlow["LOAD"]["status"].lower() == 'active'
            load_kW = currentPowerFlow["LOAD"]["currentPower"]

            pv_active = currentPowerFlow["PV"]["status"].lower() == 'active'
            pv_kW = currentPowerFlow["PV"]["currentPower"]

            lcd.clear()

            pv_to_house = ' '
            house_to_grid = ' '

            connections = currentPowerFlow["connections"]
            for connection in connections:
                source = connection["from"].lower()
                target = connection["to"].lower()
                if source == 'pv' and target == 'load':
                    pv_to_house = arrow_right_icon
                elif source == 'grid' and target == 'load':
                    house_to_grid = arrow_left_icon
                elif source == 'load' and target == 'grid':
                    house_to_grid = arrow_right_icon

            # LCD setup:
            #0123456789123456
            #L_P_→__H__←__G__
            #0.00  0.00  0.00
            lcd.write_string(f"  {pv_icon} {pv_to_house}  {house_icon}  {house_to_grid}  {grid_icon} ")
            lcd.crlf()
            lcd.write_string(f'{pv_kW:<4.3g} {load_kW:^5.4g} {grid_kW:>5.4g}')
        except requests.exceptions.HTTPError:
            print("HTTP error")
            lcd.clear()
            lcd.write_string('HTTP error')
        except:
            err = sys.exc_info()[0]
            print("Unexpected error:", err)
            lcd.clear()
            lcd.write_string(str(err))
            raise
        # The solaredge API only allows 300 calls per day
        # so we need to throttle the updates...
        time_to_sleep = round(24*60/300*60)
        print(f"Sleeping for {time_to_sleep} seconds...")
        time.sleep(time_to_sleep)
    lcd.close()
