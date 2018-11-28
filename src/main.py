from RPLCD.i2c import CharLCD
import solaredge
import os


if __name__ == '__main__':
    lcd = CharLCD(i2c_expander='PCF8574', address=0x3f, port=1,
              cols=16, rows=2, dotsize=8,
              charmap='A02',
              auto_linebreaks=True,
              backlight_enabled=True)
    #lcd.write_string('Hello world')
    #lcd.close()

    SOLAREDGE_API_KEY = os.environ['SOLAREDGE_API_KEY']
    SOLAREDGE_SITE_ID = os.environ['SOLAREDGE_SITE_ID']

    s = solaredge.Solaredge(SOLAREDGE_API_KEY)
    print(s.get_current_power_flow(SOLAREDGE_SITE_ID))

    lcd.write(s.siteCurrentPowerFlow)
    lcd.close()