from micropython import const
import framebuf  # type: ignore

SET_CONTRAST   = const(0x81)
SET_ENTIRE_ON  = const(0xa4)
SET_NORM_INV   = const(0xa6)
SET_DISP       = const(0xae)
SET_MEM_ADDR   = const(0x20)
SET_COL_ADDR   = const(0x21)
SET_PAGE_ADDR  = const(0x22)
SET_DISP_LINE  = const(0x40)
SET_SEG_REMAP  = const(0xa0)
SET_MUX_RATIO  = const(0xa8)
SET_COM_DIR    = const(0xc0)
SET_DISP_OFF   = const(0xd3)
SET_COM_PIN    = const(0xda)
SET_CLK_DIV    = const(0xd5)
SET_PRECHARGE  = const(0xd9)
SET_VCOM       = const(0xdb)
SET_PUMP       = const(0x8d)


class SSD1306:
    def __init__(self, w, h, ext_vcc):
        self.width = w
        self.height = h
        self.external_vcc = ext_vcc
        self.pages = h // 8
        self.buffer = bytearray(
            self.pages * w
        )
        fb = framebuf.FrameBuffer(
            self.buffer,
            w, h,
            framebuf.MONO_VLSB
        )
        self.framebuf  = fb
        self.fill      = fb.fill
        self.pixel     = fb.pixel
        self.hline     = fb.hline
        self.vline     = fb.vline
        self.line      = fb.line
        self.rect      = fb.rect
        self.fill_rect = fb.fill_rect
        self.text      = fb.text
        self.scroll    = fb.scroll
        self.blit      = fb.blit
        self.init_display()

    def init_display(self):
        is32 = (
            self.width == 128
            and self.height == 32
        )
        pin = 0x02 if is32 else 0x12
        pre = (
            0x22 if self.external_vcc
            else 0xF1
        )
        pump = (
            0x10 if self.external_vcc
            else 0x14
        )
        cmds = [
            SET_DISP | 0x00,
            SET_MEM_ADDR, 0x00,
            SET_DISP_LINE | 0x00,
            SET_SEG_REMAP | 0x01,
            SET_MUX_RATIO,
            self.height - 1,
            SET_COM_DIR | 0x08,
            SET_DISP_OFF, 0x00,
            SET_COM_PIN, pin,
            SET_CLK_DIV, 0x80,
            SET_PRECHARGE, pre,
            SET_VCOM, 0x30,
            SET_CONTRAST, 0xFF,
            SET_ENTIRE_ON,
            SET_NORM_INV,
            SET_PUMP, pump,
            SET_DISP | 0x01,
        ]
        for cmd in cmds:
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweroff(self):
        self.write_cmd(SET_DISP | 0x00)

    def poweron(self):
        self.write_cmd(SET_DISP | 0x01)

    def contrast(self, c):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(c)

    def invert(self, inv):
        self.write_cmd(
            SET_NORM_INV | (inv & 1)
        )

    def rotate(self, rot):
        r = rot & 1
        v = SET_COM_DIR | (r << 3)
        self.write_cmd(v)
        self.write_cmd(
            SET_SEG_REMAP | (rot & 1)
        )

    def show(self):
        x0 = 0
        x1 = self.width - 1
        if self.width != 128:
            off = (128 - self.width)
            off = off // 2
            x0 += off
            x1 += off
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(x0)
        self.write_cmd(x1)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_data(self.buffer)


class SSD1306_I2C(SSD1306):
    def __init__(
        self, w, h, i2c,
        addr=0x3C, ext_vcc=False
    ):
        self.i2c  = i2c
        self.addr = addr
        self.temp = bytearray(2)
        self.wlist = [b"\x40", None]
        super().__init__(w, h, ext_vcc)

    def write_cmd(self, cmd):
        self.temp[0] = 0x80
        self.temp[1] = cmd
        self.i2c.writeto(
            self.addr, self.temp
        )

    def write_data(self, buf):
        self.wlist[1] = buf
        self.i2c.writevto(
            self.addr, self.wlist
        )


class SSD1306_SPI(SSD1306):
    def __init__(
        self, w, h, spi,
        dc, res, cs, ext_vcc=False
    ):
        self.rate = 10 * 1024 * 1024
        dc.init(dc.OUT, value=0)
        res.init(res.OUT, value=0)
        cs.init(cs.OUT, value=1)
        self.spi = spi
        self.dc  = dc
        self.res = res
        self.cs  = cs
        import time
        self.res(1)
        time.sleep_ms(1)
        self.res(0)
        time.sleep_ms(10)
        self.res(1)
        super().__init__(w, h, ext_vcc)

    def write_cmd(self, cmd):
        self.spi.init(
            baudrate=self.rate,
            polarity=0, phase=0
        )
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, buf):
        self.spi.init(
            baudrate=self.rate,
            polarity=0, phase=0
        )
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(buf)
        self.cs(1)