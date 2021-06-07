import binascii
from icepool import icepool
import logging
import math
import struct
import time

from . import midstate

_log = logging.getLogger('shapool-client.shapool')

class Shapool:
    def __init__(self, ctx: icepool.IcepoolContext, number_of_devices: int, cores_per_device: int):
        self._ctx = ctx

        # Number of devices on IcepoolContext
        self.number_of_devices = number_of_devices
        self.hardcoded_bits = math.ceil(math.log2(cores_per_device))

        nonce_step = 0x100 // self.number_of_devices
        self.device_configs = bytes([i * nonce_step for i in range(self.number_of_devices)])

    def __del__(self):
        self._ctx.assert_reset()

    def start_execution(self):
        self._ctx.deassert_reset()
    
    def interrupt_execution(self):
        self._ctx.spi_assert_daisy()
        self._ctx.spi_deassert_daisy()

    def reset(self):
        self._ctx.assert_reset()

    def poll_until_ready_or_timeout(self, timeout_s):
        ready = False
    
        if timeout_s is None:
            while not ready:
                ready = self._ctx.poll_ready()
        else:
            start_time = time.time()
            while not ready and time.time() - start_time < timeout_s:
                ready = self._ctx.poll_ready()
    
        return ready

    def update_device_configs(self):
        self._ctx.assert_reset()
        self._ctx.spi_assert_daisy()
        self._ctx.spi_write_daisy(self.device_configs)
        self._ctx.spi_deassert_daisy()

    def update_job(self, midstate, message):
        self._ctx.assert_reset()
        self._ctx.spi_assert_shared()
        self._ctx.spi_write_shared(midstate + message)
        self._ctx.spi_deassert_shared()

    def get_result(self):
        self._ctx.spi_assert_daisy()
        results = self._ctx.spi_read_daisy(5 * self.number_of_devices)
        self._ctx.spi_deassert_daisy()

        for n_device in range(self.number_of_devices):
            result_offset = 5*n_device
            flags = results[result_offset]

            if flags != 0:
                nonce, = struct.unpack(">L", results[result_offset+1:result_offset+5])
                nonce = Shapool._correct_nonce(\
                    nonce, flags, self.device_configs[n_device], self.hardcoded_bits)
                return nonce

        return None
    
    def update_difficulty(self, difficulty):
        # TODO
        pass

    @staticmethod
    def _pack_job(version, previous_hash, merkle_root, timestamp, bits):
        # version, previous_hash, merkle_root should be bytes, already in correct order
        message = version + \
                  previous_hash + \
                  merkle_root + \
                  timestamp + \
                  bits

        return message[:64], message[64:]
    
    @staticmethod
    def _precompute_midstate(first_block):
        state = midstate.ShaState()
        state.update(first_block)
        return state.as_bin(True)

    @staticmethod
    def _correct_nonce(nonce, flags, device_offset, hardcoded_bits):
        mapping = {
            0x01: 0x0000_0000,
            0x02: 0x0000_0001,
            0x04: 0x0000_0002,
            0x08: 0x0000_0003,
            0x10: 0x0000_0004,
            0x20: 0x0000_0005,
            0x40: 0x0000_0006,
            0x80: 0x0000_0007
        }

        nonce -= 2
        nonce |= mapping[flags] << (32-hardcoded_bits)
        nonce ^= device_offset << (32-hardcoded_bits-8)

        return nonce
