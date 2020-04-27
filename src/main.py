from RPLCD.i2c import CharLCD
import solaredge
import os
import requests
import sys
from time import sleep
from datetime import datetime, timedelta, time, timezone
from suntime import Sun
from dateutil.tz import tzlocal
import re
import logging
import pytz

MAX_SERVICE_CALLS_PER_DAY=300
OVERVIEW_INTERVAL_MINUTES=15
logger = logging.getLogger('solarEdgeDisplay')
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)

def is_time_between(begin_time, end_time, check_time=None):
    # If check time is not given, default to current UTC time
    check_time = check_time or datetime.utcnow().time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else: # crosses midnight
        return check_time >= begin_time or check_time <= end_time

if __name__ == '__main__':
    if 'LOG_LEVEL' in os.environ:
        log_level = os.environ['LOG_LEVEL']
        logger.info(f'Setting log level to {log_level}')
        logger.setLevel(log_level)

    if 'DIMENSIONS' in os.environ:
        DIMENSIONS = os.environ['DIMENSIONS']
        if DIMENSIONS != '16x2' and DIMENSIONS != '20x4':
            logger.error(f"Unknown dimensions {DIMENSIONS}")
            sys.exit(1)
        logger.debug(f"Dimensions set to {DIMENSIONS}")
    else:
        logger.debug("Dimension defaulted to 16x2")
        DIMENSIONS = '16x2'

    if 'DISPLAY_ADDRESS_HEX' in os.environ:
        DISPLAY_ADDRESS = int(os.environ['DISPLAY_ADDRESS_HEX'],16)
    else:
        logger.error('DISPLAY_ADDRESS_HEX missing')
        sys.exit(1)

    cols, rows = [int(n) for n in DIMENSIONS.split('x')]

    lcd = CharLCD(i2c_expander='PCF8574', address=DISPLAY_ADDRESS, port=1,
              cols=cols, rows=rows, dotsize=8,
              charmap='A02',
              auto_linebreaks=True,
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

    bitmap_error = (
        0b00000,
        0b01110,
        0b10101,
        0b10101,
        0b10101,
        0b01110,
        0b00000,
        0b00000
    )
    lcd.create_char(4, bitmap_error)
    

    pv_icon = '\x01'
    arrow_right_icon = '\x7E'
    house_icon = '\x00'
    arrow_left_icon = '\x03'
    grid_icon = '\x02'
    loading_icon = '\x04'
    error_icon = '\x05'

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
    if 'BACKLIGHT_MODE' in os.environ:
        backlight_mode = os.environ['BACKLIGHT_MODE']

    # coordinates via https://www.latlong.net/
    if 'LONGITUDE' in os.environ:
        LONGITUDE = os.environ['LONGITUDE']
    else:
        logger.error('LONGITUDE missing')
        sys.exit(1)

    if 'LATITUDE' in os.environ:
        LATITUDE = os.environ['LATITUDE']
    else:
        logger.error('LATITUDE missing')
        sys.exit(1)
    sun = Sun(float(LATITUDE), float(LONGITUDE))

    if 'TIMEZONE' in os.environ:
        TIMEZONE = os.environ['TIMEZONE']
    else:
        lcd.clear()
        lcd.write_string('TIMEZONE missing')
        sys.exit(1)

    lcd.clear()
    error = None
    exponential_backoff=1

    day_kWh = None
    month_kWh = None
    year_kWh = None
    last_update = None

    local_now = datetime.now(pytz.timezone(TIMEZONE))
    tz_string = local_now.strftime('%z')
    tz_hours = local_now.utcoffset().total_seconds()/60/60

    while True:
        now = datetime.now(timezone.utc)
        logger.debug(f'current date and time: {now}')
        # TODO: use TZ here
        today_sunrise = sun.get_sunrise_time(now + timedelta(0,0,0,0,0,tz_hours) - timedelta(1))
        logger.debug(f'sunrise is: {today_sunrise}')
        # TODO: use TZ here
        today_sunset = sun.get_sunset_time(now + timedelta(0,0,0,0,0,tz_hours))
        logger.debug(f'sunset is: {today_sunset}')
        is_night = now < today_sunrise or now > today_sunset
        is_day = not is_night
        day_hours = round((today_sunset - today_sunrise).total_seconds() / 3600)

        try:
            if backlight_mode == 'night':
                lcd.backlight_enabled = is_night
                logger.debug(f"Backlight is enabled: {lcd.backlight_enabled}")

            lcd.home()
            if error != None:
                lcd.clear()
                error = None
            lcd.write_string(loading_icon)
            logger.debug('loading data...')
            currentPowerFlow = s.get_current_power_flow(SOLAREDGE_SITE_ID)["siteCurrentPowerFlow"]
            logger.debug('current power flow:')
            logger.debug(currentPowerFlow)
            grid_active = currentPowerFlow["GRID"]["status"].lower() == 'active'
            grid_kW = currentPowerFlow["GRID"]["currentPower"]

            load_active = currentPowerFlow["LOAD"]["status"].lower() == 'active'
            load_kW = currentPowerFlow["LOAD"]["currentPower"]

            pv_active = currentPowerFlow["PV"]["status"].lower() == 'active'
            pv_kW = currentPowerFlow["PV"]["currentPower"]

            if DIMENSIONS == '20x4':
                logger.debug(f'last update was: {last_update}')
                if is_time_between(time(0), time(1), now.time()):
                    # reset the day KW at midnight
                    day_kWh = 0
                elif last_update is None or (is_day and (now - last_update).seconds > OVERVIEW_INTERVAL_MINUTES*60):
                    overview = s.get_overview(SOLAREDGE_SITE_ID)["overview"]
                    logger.debug('overview:')
                    logger.debug(overview)
                    day_kWh = overview["lastDayData"]["energy"] / 1000
                    logger.debug(f'  day kWh: {day_kWh}')
                    month_kWh = overview["lastMonthData"]["energy"] / 1000
                    logger.debug(f'month kWh: {month_kWh}')
                    year_kWh = overview["lastYearData"]["energy"] / 1000
                    logger.debug(f' year kWh: {year_kWh}')
                    lastUpdateTime = overview["lastUpdateTime"]
                    last_update = datetime.strptime(f'{lastUpdateTime}{tz_string}', '%Y-%m-%d %H:%M:%S%z')
                else:
                    logger.debug(f'not time to update yet:')
                    logger.debug(f'is day:          {is_day}')
                    logger.debug(f'seconds:         {(now - last_update).seconds}')
                    logger.debug(f'seconds to wait: {OVERVIEW_INTERVAL_MINUTES*60}')

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
                    f"  {pv_icon} {pv_to_house}  {house_icon}  {house_to_grid}  {grid_icon}  ",
                    f'{pv_kW:<4.3g} {load_kW:^5.4g} {grid_kW:>5.4g}'
                ]
            else:
                #01234567890123456789
                #L__P__→___H___←__G__
                #0.000__0.000___0.000
                #Day____Month__Year__
                #000.00_0000.0_0000.0
                lines = [
                    f"   {pv_icon}  {pv_to_house}   {house_icon}   {house_to_grid}  {grid_icon}  ",
                    f'{pv_kW:<5.4g} {load_kW:^6.5g}  {grid_kW:>6.5g}',
                    'Day   Month   Year  ',
                    f'{day_kWh:<5.4g} {month_kWh:<6.5g}  {year_kWh:<6.5g}'
                ]
            if logger.level == logging.DEBUG:
                for line in lines:
                    line = line[:cols]
                    logger.debug('|' + '-' * cols + '|')
                    logger.debug('|' + re.sub(r'[\x00-\x09\x7E]+', '#', line).replace(' ', '_') + '|')

            lcd.clear()
            for num, line in enumerate(lines, start=0):
                lcd.cursor_pos = (num,0)
                line = line[:cols]
                lcd.write_string(line)
            # everything was fine; reset exponential backoff
            exponential_backoff=1
        except requests.exceptions.HTTPError as e:
            logger.error("Unexpected HTTP error: %s", str(e))
            lcd.home()
            lcd.write_string(error_icon)
            exponential_backoff = min(exponential_backoff*2,16)
            logger.info(f'Increased exponential backoff: {exponential_backoff}')
        except Exception as e:
            logger.error("Unexpected error: %s", str(e))
            lcd.clear()
            lcd.auto_linebreaks = True
            lcd.write_string(str(e))
            error = e
            exponential_backoff = min(exponential_backoff*2,16)
            logger.info(f'Increased exponential backoff: {exponential_backoff}')

        extra_calls_per_day=0
        if DIMENSIONS == '20x4':
            # there is one extra request every OVERVIEW_INTERVAL_MINUTES minutes during sun hours for the overview data
            extra_calls_per_day=day_hours*60/OVERVIEW_INTERVAL_MINUTES

        # The solaredge API only allows MAX_SERVICE_CALLS_PER_DAY calls per day
        # so we need to throttle the updates...
        secs_to_sleep = round(24*60*60/(MAX_SERVICE_CALLS_PER_DAY - extra_calls_per_day) * exponential_backoff)
        logger.info(f"Sleeping for {secs_to_sleep} seconds...")
        sleep(secs_to_sleep)
    lcd.close()
