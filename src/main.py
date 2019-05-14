from RPLCD.i2c import CharLCD
import solaredge
import os
import time
import requests
import sys
from datetime import datetime, timedelta
from suntime import Sun
from dateutil.tz import tzlocal
import re


if __name__ == '__main__':
    if 'DIMENSIONS' in os.environ:
        DIMENSIONS = os.environ['DIMENSIONS']
        if DIMENSIONS != '16x2' and DIMENSIONS != '20x4':
            print(f"Unknown dimensions {DIMENSIONS}")
            sys.exit(1)
        print(f"Dimensions set to {DIMENSIONS}")
    else:
        print("Dimension defaulted to 16x2")
        DIMENSIONS = '16x2'

    cols, rows = [int(n) for n in DIMENSIONS.split('x')]

    lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1,
              cols=cols, rows=rows, dotsize=8,
              charmap='A02',
              auto_linebreaks=False,
              backlight_enabled=True)
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

    backlight_mode = 'always' # default
    sun = None
    if 'BACKLIGHT_MODE' in os.environ:
        backlight_mode = os.environ['BACKLIGHT_MODE']

        if backlight_mode == 'night':
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
            if backlight_mode == 'night':
                now = datetime.now(tzlocal())
                # We get the day before today and then its sunrise, which is the sunrise leading up to now
                today_sr = sun.get_local_sunrise_time(datetime.today() - timedelta(1))
                today_ss = sun.get_local_sunset_time(datetime.today())
                lcd.backlight_enabled = now < today_sr or now > today_ss
                print(f"Backlight is enabled: {lcd.backlight_enabled}")

            lcd.home()
            lcd.write_string(loading_icon)
            print('loading data')
            print('current power flow')
            currentPowerFlow = s.get_current_power_flow(SOLAREDGE_SITE_ID)["siteCurrentPowerFlow"]
            print(currentPowerFlow)
            grid_active = currentPowerFlow["GRID"]["status"].lower() == 'active'
            grid_kW = currentPowerFlow["GRID"]["currentPower"]

            load_active = currentPowerFlow["LOAD"]["status"].lower() == 'active'
            load_kW = currentPowerFlow["LOAD"]["currentPower"]

            pv_active = currentPowerFlow["PV"]["status"].lower() == 'active'
            pv_kW = currentPowerFlow["PV"]["currentPower"]
            day_kWh = None
            month_kWh = None
            year_kWh = None
            last_update = None
            if DIMENSIONS == '20x4' and (last_update is None or (datetime.now(tzlocal()) - last_update).seconds > 15*60):
                print('overview')
                overview = s.get_overview(SOLAREDGE_SITE_ID)["overview"]
                print(overview)
                day_kWh = overview["lastDayData"]["energy"] / 1000
                print(f'day kWh: {day_kWh}')
                month_kWh = overview["lastMonthData"]["energy"] / 1000
                print(f'month kWh: {month_kWh}')
                year_kWh = overview["lastYearData"]["energy"] / 1000
                print(f'year kWh: {year_kWh}')
                last_update = datetime.strptime(overview["lastUpdateTime"], '%Y-%m-%d %H:%M:%S')

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
            lines = None
            if DIMENSIONS == '16x2':
                #0123456789123456
                #L_P_→__H__←__G__
                #0.00__0.00__0.00
                lines = [
                    f"  {pv_icon} {pv_to_house}  {house_icon}  {house_to_grid}  {grid_icon} ",
                    f'{pv_kW:<4.3g} {load_kW:^5.4g} {grid_kW:>5.4g}'
                ]
            else:
                #01234567890123456789
                #L__P__→___H___←__G__
                #0.000__0.000___0.000
                #Day___|Month_|Year__
                #000.00|_000.0|0000.0
                lines = [
                    f"   {pv_icon}  {pv_to_house}   {house_icon}   {house_to_grid}  {grid_icon} ",
                    f'{pv_kW:<5.4g} {load_kW:^6.5g}  {grid_kW:>6.5g}',
                    'Day   |Month |Year  ',
                    f'{day_kWh:<3g}|{month_kWh:^3g}|{year_kWh:>4g}'
                ]

            #lcd.clear()
            lcd.home()
            for line in lines:
                line = line[:cols]
                print('|' + '-' * cols + '|')
                print('|' + re.sub(r'[\x00-\x7F]+', '#', line).replace(' ', '_') + '|')
                #lcd.write_string(line)
                #lcd.crlf()
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

        extra_calls_per_day=0
        if DIMENSIONS == '20x4':
            # there is one extra request every 15 minutes for the overview data
            extra_calls_per_day=24*60/15

        # The solaredge API only allows 300 calls per day
        # so we need to throttle the updates...
        secs_to_sleep = round(24*60*60/(300-extra_calls_per_day))
        print(f"Sleeping for {secs_to_sleep} seconds...")
        time.sleep(secs_to_sleep)
    lcd.close()
