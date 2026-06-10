"""
MicroPython driver for SD cards using SPI bus.

Requires an SPI bus and a CS pin.  Provides readblocks and writeblocks
methods so the device can be mounted as a filesystem.

Example usage on pyboard:

    import pyb, sdcard, os
    sd = sdcard.SDCard(pyb.SPI(1), pyb.Pin.board.X5)
    pyb.mount(sd, '/sd2')
    os.listdir('/')

Example usage on ESP8266:

    import machine, sdcard, os
    sd = sdcard.SDCard(machine.SPI(1), machine.Pin(15))
    os.mount(sd, '/sd')
    os.listdir('/')

"""

from micropython import const
import machine
import os
import time


_CMD_TIMEOUT = const(100)

_R1_IDLE_STATE = const(1 << 0)
# R1_ERASE_RESET = const(1 << 1)
_R1_ILLEGAL_COMMAND = const(1 << 2)
# R1_COM_CRC_ERROR = const(1 << 3)
# R1_ERASE_SEQUENCE_ERROR = const(1 << 4)
# R1_ADDRESS_ERROR = const(1 << 5)
# R1_PARAMETER_ERROR = const(1 << 6)
_TOKEN_CMD25 = const(0xFC)
_TOKEN_STOP_TRAN = const(0xFD)
_TOKEN_DATA = const(0xFE)

MISO_PIN = 0
CS_PIN = 1
SCK_PIN = 2
MOSI_PIN = 3
CD_PIN = 4

DEFAULT_MOUNT_POINT = "/sd"
DEFAULT_SPI_BAUDRATE = 20_000_000

_mounted = False
_mount_point = DEFAULT_MOUNT_POINT
_sd = None


def _crc7(buf, n):
    crc = 0
    for i in range(n):
        crc ^= buf[i]
        for j in range(8):
            crc = ((crc << 1) ^ (0x12 * (crc >> 7))) & 0xFF
    return crc


class SDCard:
    def __init__(self, spi, cs, baudrate=DEFAULT_SPI_BAUDRATE):
        self.spi = spi
        self.cs = cs

        self.cmdbuf = bytearray(6)
        self.dummybuf = bytearray(512)
        self.tokenbuf = bytearray(1)
        for i in range(512):
            self.dummybuf[i] = 0xFF
        self.dummybuf_memoryview = memoryview(self.dummybuf)

        # initialise the card
        self.init_card(baudrate)

    def init_spi(self, baudrate):
        try:
            master = self.spi.MASTER
        except AttributeError:
            # on ESP8266
            self.spi.init(baudrate=baudrate, phase=0, polarity=0)
        else:
            # on pyboard
            self.spi.init(master, baudrate=baudrate, phase=0, polarity=0)

    def init_card(self, baudrate):
        # init CS pin
        self.cs.init(self.cs.OUT, value=1)

        # init SPI bus; use low data rate for initialisation
        self.init_spi(100000)

        # clock card at least 100 cycles with cs high
        for i in range(16):
            self.spi.write(b"\xff")

        # CMD0: init card; should return _R1_IDLE_STATE (allow 5 attempts)
        for _ in range(5):
            if self.cmd(0, 0) == _R1_IDLE_STATE:
                break
        else:
            raise OSError("no SD card")

        # CMD8: determine card version
        r = self.cmd(8, 0x01AA, 4)
        if r == _R1_IDLE_STATE:
            self.init_card_v2()
        elif r == (_R1_IDLE_STATE | _R1_ILLEGAL_COMMAND):
            self.init_card_v1()
        else:
            raise OSError("couldn't determine SD card version")

        # get the number of sectors
        # CMD9: response R2 (R1 byte + 16-byte block read)
        if self.cmd(9, 0, 0, False) != 0:
            raise OSError("no response from SD card")
        csd = bytearray(16)
        self.readinto(csd)
        if csd[0] & 0xC0 == 0x40:  # CSD version 2.0
            self.sectors = ((csd[7] << 16 | csd[8] << 8 | csd[9]) + 1) * 1024
        elif csd[0] & 0xC0 == 0x00:  # CSD version 1.0 (old, <=2GB)
            c_size = (csd[6] & 0b11) << 10 | csd[7] << 2 | csd[8] >> 6
            c_size_mult = (csd[9] & 0b11) << 1 | csd[10] >> 7
            read_bl_len = csd[5] & 0b1111
            capacity = (c_size + 1) * (2 ** (c_size_mult + 2)) * (2**read_bl_len)
            self.sectors = capacity // 512
        else:
            raise OSError("SD card CSD format not supported")
        # print('sectors', self.sectors)

        # CMD16: set block length to 512 bytes
        if self.cmd(16, 512) != 0:
            raise OSError("can't set 512 block size")

        # set to high data rate now that it's initialised
        self.init_spi(baudrate)

    def init_card_v1(self):
        for i in range(_CMD_TIMEOUT):
            time.sleep_ms(50)
            self.cmd(55, 0)
            if self.cmd(41, 0) == 0:
                # SDSC card, uses byte addressing in read/write/erase commands
                self.cdv = 512
                # print("[SDCard] v1 card")
                return
        raise OSError("timeout waiting for v1 card")

    def init_card_v2(self):
        for i in range(_CMD_TIMEOUT):
            time.sleep_ms(50)
            self.cmd(58, 0, 4)
            self.cmd(55, 0)
            if self.cmd(41, 0x40000000) == 0:
                self.cmd(58, 0, -4)  # 4-byte response, negative means keep the first byte
                ocr = self.tokenbuf[0]  # get first byte of response, which is OCR
                if not ocr & 0x40:
                    # SDSC card, uses byte addressing in read/write/erase commands
                    self.cdv = 512
                else:
                    # SDHC/SDXC card, uses block addressing in read/write/erase commands
                    self.cdv = 1
                # print("[SDCard] v2 card")
                return
        raise OSError("timeout waiting for v2 card")

    def cmd(self, cmd, arg, final=0, release=True, skip1=False):
        self.cs(0)

        # create and send the command
        buf = self.cmdbuf
        buf[0] = 0x40 | cmd
        buf[1] = arg >> 24
        buf[2] = arg >> 16
        buf[3] = arg >> 8
        buf[4] = arg
        buf[5] = _crc7(buf, 5) | 0x01  # ensure stop bit is always set
        self.spi.write(buf)

        if skip1:
            self.spi.readinto(self.tokenbuf, 0xFF)

        # wait for the response (response[7] == 0)
        for i in range(_CMD_TIMEOUT):
            self.spi.readinto(self.tokenbuf, 0xFF)
            response = self.tokenbuf[0]
            if not (response & 0x80):
                # this could be a big-endian integer that we are getting here
                # if final<0 then store the first byte to tokenbuf and discard the rest
                if final < 0:
                    self.spi.readinto(self.tokenbuf, 0xFF)
                    final = -1 - final
                for j in range(final):
                    self.spi.write(b"\xff")
                if release:
                    self.cs(1)
                    self.spi.write(b"\xff")
                return response

        # timeout
        self.cs(1)
        self.spi.write(b"\xff")
        return -1

    def readinto(self, buf):
        self.cs(0)

        # read until start byte (0xff)
        for i in range(_CMD_TIMEOUT):
            self.spi.readinto(self.tokenbuf, 0xFF)
            if self.tokenbuf[0] == _TOKEN_DATA:
                break
            time.sleep_ms(1)
        else:
            self.cs(1)
            raise OSError("timeout waiting for response")

        # read data
        mv = self.dummybuf_memoryview
        if len(buf) != len(mv):
            mv = mv[: len(buf)]
        self.spi.write_readinto(mv, buf)

        # read checksum
        self.spi.write(b"\xff")
        self.spi.write(b"\xff")

        self.cs(1)
        self.spi.write(b"\xff")

    def write(self, token, buf):
        self.cs(0)

        # send: start of block, data, checksum
        self.spi.read(1, token)
        self.spi.write(buf)
        self.spi.write(b"\xff")
        self.spi.write(b"\xff")

        # check the response
        if (self.spi.read(1, 0xFF)[0] & 0x1F) != 0x05:
            self.cs(1)
            self.spi.write(b"\xff")
            return

        # wait for write to finish
        while self.spi.read(1, 0xFF)[0] == 0:
            pass

        self.cs(1)
        self.spi.write(b"\xff")

    def write_token(self, token):
        self.cs(0)
        self.spi.read(1, token)
        self.spi.write(b"\xff")
        # wait for write to finish
        while self.spi.read(1, 0xFF)[0] == 0x00:
            pass

        self.cs(1)
        self.spi.write(b"\xff")

    def readblocks(self, block_num, buf):
        # workaround for shared bus, required for (at least) some Kingston
        # devices, ensure MOSI is high before starting transaction
        self.spi.write(b"\xff")

        nblocks = len(buf) // 512
        assert nblocks and not len(buf) % 512, "Buffer length is invalid"
        if nblocks == 1:
            # CMD17: set read address for single block
            if self.cmd(17, block_num * self.cdv, release=False) != 0:
                # release the card
                self.cs(1)
                raise OSError(5)  # EIO
            # receive the data and release card
            self.readinto(buf)
        else:
            # CMD18: set read address for multiple blocks
            if self.cmd(18, block_num * self.cdv, release=False) != 0:
                # release the card
                self.cs(1)
                raise OSError(5)  # EIO
            offset = 0
            mv = memoryview(buf)
            while nblocks:
                # receive the data and release card
                self.readinto(mv[offset : offset + 512])
                offset += 512
                nblocks -= 1
            if self.cmd(12, 0, skip1=True):
                raise OSError(5)  # EIO

    def writeblocks(self, block_num, buf):
        # workaround for shared bus, required for (at least) some Kingston
        # devices, ensure MOSI is high before starting transaction
        self.spi.write(b"\xff")

        nblocks, err = divmod(len(buf), 512)
        assert nblocks and not err, "Buffer length is invalid"
        if nblocks == 1:
            # CMD24: set write address for single block
            if self.cmd(24, block_num * self.cdv) != 0:
                raise OSError(5)  # EIO

            # send the data
            self.write(_TOKEN_DATA, buf)
        else:
            # CMD25: set write address for first block
            if self.cmd(25, block_num * self.cdv) != 0:
                raise OSError(5)  # EIO
            # send the data
            offset = 0
            mv = memoryview(buf)
            while nblocks:
                self.write(_TOKEN_CMD25, mv[offset : offset + 512])
                offset += 512
                nblocks -= 1
            self.write_token(_TOKEN_STOP_TRAN)

    def ioctl(self, op, arg):
        if op == 4:  # get number of blocks
            return self.sectors
        if op == 5:  # get block size in bytes
            return 512


def card_present():
    """Return True when the active-low card detect pin sees a card."""
    return machine.Pin(CD_PIN, machine.Pin.IN).value() == 0


def _mount_point_is_mounted(mount_point):
    try:
        os.listdir(mount_point)
        return True
    except OSError:
        return False


def mount(mount_point=DEFAULT_MOUNT_POINT, baudrate=DEFAULT_SPI_BAUDRATE):
    """Mount the SD card and return the SDCard block device."""
    global _mounted, _mount_point, _sd

    if _mounted:
        print("SD card is already mounted")
        return _sd

    if _mount_point_is_mounted(mount_point):
        print("SD card is already mounted")
        _mounted = True
        _mount_point = mount_point
        return _sd

    if not card_present():
        raise OSError("no SD card detected")

    spi = machine.SPI(
        0,
        baudrate=100000,
        sck=machine.Pin(SCK_PIN),
        mosi=machine.Pin(MOSI_PIN),
        miso=machine.Pin(MISO_PIN),
    )
    cs = machine.Pin(CS_PIN, machine.Pin.OUT, value=1)

    sd = SDCard(spi, cs, baudrate=baudrate)
    try:
        os.mount(sd, mount_point)
    except OSError as e:
        if "already mounted" in str(e).lower():
            print("SD card is already mounted")
            _mounted = True
            _mount_point = mount_point
            _sd = sd
            return sd
        raise

    _mounted = True
    _mount_point = mount_point
    _sd = sd
    return sd


def unmount():
    """Unmount the SD card."""
    global _mounted, _sd
    if not _mounted:
        raise OSError("SD card is not mounted")
    os.umount(_mount_point)
    _mounted = False
    _sd = None


def is_mounted():
    return _mounted


def _full_path(name=""):
    """Convert a user-facing SD path into the real MicroPython path."""
    if not name or name == "/":
        return _mount_point
    if name.startswith(_mount_point + "/") or name == _mount_point:
        return name
    return _mount_point.rstrip("/") + "/" + name.lstrip("/")


def _relative_path(name):
    """Remove the mount point from a path before showing it to the caller."""
    prefix = _mount_point.rstrip("/") + "/"
    if name.startswith(prefix):
        return name[len(prefix) :]
    if name == _mount_point:
        return ""
    return name


def exists(filename):
    try:
        os.stat(_full_path(filename))
        return True
    except OSError:
        return False


def is_dir(filename):
    try:
        return bool(os.stat(_full_path(filename))[0] & 0x4000)
    except OSError:
        return False


def mkdir(dirname):
    if not exists(dirname):
        os.mkdir(_full_path(dirname))


def list_dir(dirname=""):
    return os.listdir(_full_path(dirname))


def list_files(root=""):
    """Return every file under root, relative to the SD card root."""
    files = []

    def walk(dirname):
        for name in os.listdir(dirname):
            full_path = dirname.rstrip("/") + "/" + name
            if is_dir(_relative_path(full_path)):
                walk(full_path)
            else:
                files.append(_relative_path(full_path))

    walk(_full_path(root))
    return files


def print_tree(root=""):
    for filename in list_files(root):
        print(filename)


def read_text(filename):
    with open(_full_path(filename), "r") as f:
        return f.read()


def write_text(filename, text):
    with open(_full_path(filename), "w") as f:
        f.write(text)


def append_text(filename, text):
    with open(_full_path(filename), "a") as f:
        f.write(text)


def read_bytes(filename):
    with open(_full_path(filename), "rb") as f:
        return f.read()


def open_file(filename, mode="r"):
    return open(_full_path(filename), mode)


def write_bytes(filename, data):
    with open(_full_path(filename), "wb") as f:
        f.write(data)


def remove(filename):
    os.remove(_full_path(filename))


def rename(old_filename, new_filename):
    os.rename(_full_path(old_filename), _full_path(new_filename))


def file_size(filename):
    return os.stat(_full_path(filename))[6]


def read_wav_info(filename):
    """Read basic metadata from a PCM WAV file without loading all audio."""
    with open(_full_path(filename), "rb") as f:
        header = f.read(12)
        if header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise ValueError("not a WAV file")

        info = {"audio_format": None, "channels": None, "sample_rate": None}
        info["bits_per_sample"] = None
        info["data_size"] = 0
        info["data_offset"] = None
        offset = 12

        while True:
            chunk_header = f.read(8)
            if len(chunk_header) < 8:
                break
            offset += 8

            chunk_id = chunk_header[0:4]
            chunk_size = int.from_bytes(chunk_header[4:8], "little")

            if chunk_id == b"fmt ":
                fmt = f.read(chunk_size)
                offset += chunk_size
                info["audio_format"] = int.from_bytes(fmt[0:2], "little")
                info["channels"] = int.from_bytes(fmt[2:4], "little")
                info["sample_rate"] = int.from_bytes(fmt[4:8], "little")
                info["bits_per_sample"] = int.from_bytes(fmt[14:16], "little")
            elif chunk_id == b"data":
                info["data_size"] = chunk_size
                info["data_offset"] = offset
                break
            else:
                offset += chunk_size
                f.seek(offset)

            if chunk_size & 1:
                offset += 1
                f.seek(offset)

    return info
