from RPLCD.i2c import CharLCD

if __name__ == '__main__':
    lcd = CharLCD(i2c_expander='PCF8574', address=0x3f, port=1,
              cols=16, rows=2, dotsize=8,
              charmap='A02',
              auto_linebreaks=True,
              backlight_enabled=True)
    lcd.clear()
    lcd.write_string('Hello world')
    lcd.close()