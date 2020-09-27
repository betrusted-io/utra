#![cfg_attr(target_os = "none", no_std)]
use core::convert::TryInto;
pub struct Register {
    /// Offset of this register within this CSR
    offset: usize,
}

impl Register {
    pub const fn new(offset: usize) -> Register {
        Register { offset }
    }
}

pub struct Field {
    /// A bitmask we use to AND to the value, unshifted.
    /// E.g. for a width of `3` bits, this mask would be 0b111.
    mask: usize,

    /// Offset of the first bit in this field
    offset: usize,

    /// A copy of the register address that this field
    /// is a member of. Ideally this is optimized out by the
    /// compiler.
    register: Register,
}

impl Field {
    /// Define a new CSR field with the given width at a specified
    /// offset from the start of the register.
    pub const fn new(width: usize, offset: usize, register: Register) -> Field {
        // Asserts don't work in const fn yet.
        // assert!(width != 0, "field width cannot be 0");
        // assert!((width + offset) < 32, "field with and offset must fit within a 32-bit value");

        // It would be lovely if we could call `usize::pow()` in a const fn.
        let mask = match width {
            0 => 0,
            1 => 1,
            2 => 3,
            3 => 7,
            4 => 15,
            5 => 31,
            6 => 63,
            7 => 127,
            8 => 255,
            9 => 511,
            10 => 1023,
            11 => 2047,
            12 => 4095,
            13 => 8191,
            14 => 16383,
            15 => 32767,
            16 => 65535,
            17 => 131071,
            18 => 262143,
            19 => 524287,
            20 => 1048575,
            21 => 2097151,
            22 => 4194303,
            23 => 8388607,
            24 => 16777215,
            25 => 33554431,
            26 => 67108863,
            27 => 134217727,
            28 => 268435455,
            29 => 536870911,
            30 => 1073741823,
            31 => 2147483647,
            _ => 0,
        };
        Field {
            mask,
            offset,
            register,
        }
    }
}

pub struct CSR<T> {
    base: *mut T,
}

impl<T> CSR<T>
where
    T: core::convert::TryFrom<usize> + core::convert::TryInto<usize> + core::default::Default,
{
    pub fn new(base: *mut T) -> Self {
        CSR { base }
    }

    /// Read the contents of this register
    pub fn r(&mut self, reg: Register) -> T {
        let usize_base: *mut usize = unsafe { core::mem::transmute(self.base) };
        unsafe { usize_base.add(reg.offset).read_volatile() }
            .try_into()
            .unwrap_or_default()
    }

    /// Read a field from this CSR
    pub fn rf(&mut self, field: Field) -> T {
        let usize_base: *mut usize = unsafe { core::mem::transmute(self.base) };
        ((unsafe { usize_base.add(field.register.offset).read_volatile() } >> field.offset)
            & field.mask)
            .try_into()
            .unwrap_or_default()
    }

    /// Read-modify-write a given field in this CSR
    pub fn rmwf(&mut self, field: Field, value: T) {
        let usize_base: *mut usize = unsafe { core::mem::transmute(self.base) };
        let value_as_usize: usize = value.try_into().unwrap_or_default() << field.offset;
        let previous =
            unsafe { usize_base.add(field.register.offset).read_volatile() } & !field.mask;
        unsafe {
            usize_base
                .add(field.register.offset)
                .write_volatile(previous | value_as_usize)
        };
    }

    /// Write a given field without reading it first
    pub fn wf(&mut self, field: Field, value: T) {
        let usize_base: *mut usize = unsafe { core::mem::transmute(self.base) };
        let value_as_usize: usize = value.try_into().unwrap_or_default() << field.offset;
        unsafe {
            usize_base
                .add(field.register.offset)
                .write_volatile(value_as_usize)
        };
    }

    /// Write the entire contents of a register without reading it first
    pub fn w(&mut self, reg: Register, value: T) {
        let usize_base: *mut usize = unsafe { core::mem::transmute(self.base) };
        let value_as_usize: usize = value.try_into().unwrap_or_default();
        unsafe { usize_base.add(reg.offset).write_volatile(value_as_usize) };
    }
}

#[cfg(test)]
mod tests {
    pub mod pac {
        pub mod audio {
            pub const RX_CTL: crate::Register = crate::Register::new(0x0c);
            pub const RX_CTL_ENABLE: crate::Field = crate::Field::new(1, 0, RX_CTL);
            pub const RX_CTL_RESET: crate::Field = crate::Field::new(1, 1, RX_CTL);
        }
        pub mod uart {
            pub const RXTX: crate::Register = crate::Register::new(0x00);
            pub const RXTX_RXTX: crate::Field = crate::Field::new(8, 0, RXTX);

            pub const TXFULL: crate::Register = crate::Register::new(0x04);
            pub const TXFULL_TXFULL: crate::Field = crate::Field::new(1, 0, TXFULL);
        }
    }
    #[test]
    fn compile_check() {
        use super::*;

        // Audio tests

        // The audio block is a pointer to *mut 32.
        let mut audio = CSR::new(0x1000_0000 as *mut u32);

        // Read the entire contents of the RX_CTL register
        audio.r(pac::audio::RX_CTL);

        // Or read just one field
        audio.rf(pac::audio::RX_CTL_ENABLE);

        // Do a read-modify-write of the specified field
        audio.rmwf(pac::audio::RX_CTL_RESET, 1);

        // UART tests

        // Create the UART register as a pointer to *mut u8
        let mut uart = CSR::new(0x1001_0000 as *mut u8);

        // Write the RXTX field of the RXTX register
        uart.wf(pac::uart::RXTX_RXTX, b'a');

        // Or you can write the whole UART register
        uart.w(pac::uart::RXTX, b'a');
        assert_ne!(uart.rf(pac::uart::TXFULL_TXFULL), 1);

        // Anomalies

        // This compiles but requires a cast since `audio` is a pointer to
        // u32, whereas `uart` is a pointer to u8.
        audio.wf(pac::uart::RXTX_RXTX, b'a' as _);

        // This also compiles, despite the fact that the register offset is
        // mismatched and nonsensical
        audio.wf(pac::uart::TXFULL_TXFULL, 1);
    }
}
