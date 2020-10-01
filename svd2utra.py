#!/usr/bin/python3

import xml.etree.ElementTree as ET
import argparse
from pathlib import Path, PosixPath
from datetime import datetime

def generate(fname, oname='utra'):
    Path.mkdir(PosixPath('./{}'.format(oname)), exist_ok=True)
    Path.mkdir(PosixPath('./{}/src'.format(oname)), exist_ok=True)
    toml = PosixPath('./{}/Cargo.toml'.format(oname)).open(mode='w')
    make_toml(toml, fname)

    lib = PosixPath('./{}/src/lib.rs'.format(oname)).open(mode='w')
    svd = ET.parse(fname)
    svd_root = svd.getroot()

    memoryRegions = svd_root.findall('.//vendorExtensions/memoryRegions/memoryRegion')
    peripherals = svd_root.findall('.//peripherals/peripheral')

    lib.write('// Auto-genarated by svd2utra.py from {} on {}\n'.format(fname, datetime.now().strftime("%m/%d/%Y, %H:%M:%S")))

    add_header(lib)

    lib.write('\n/////// physical base addresses of memory regions\n')
    for region in memoryRegions:
        name = region.find('name')
        base = region.find('baseAddress')
        size = region.find('size')
        lib.write('pub const HW_' + name.text + '_MEM :     u32 = ' + '{};\n'.format(base.text) )
        lib.write('pub const HW_' + name.text + '_MEM_LEN : u32 = ' + '{};\n'.format(size.text) )

    lib.write('\n\n/////// physical base addresses of registers\n')
    for peripheral in peripherals:
        peri_name = peripheral.find('name')
        base = peripheral.find('baseAddress')
        lib.write('pub const HW_' + peri_name.text + '_BASE :   u32 = ' + '{};\n'.format(base.text) )

    lib.write('\n\n')
    lib.write('pub mod utra {\n')
    for peripheral in peripherals:
        registers = peripheral.find('registers')
        peri_name = peripheral.find('name')
        lib.write('    pub mod ' + peri_name.text.lower() + ' {\n')
        for register in registers:
            name = register.find('name')
            offset = register.find('addressOffset')
            register_name = name.text
            lib.write('        pub const ' + register_name + ': crate::Register = crate::Register::new({});\n'.format(offset.text))
            for fields in register.find('fields'):
                field = fields.find('name')
                lsb = fields.find('lsb')
                msb = fields.find('msb')
                lib.write('        pub const ' + register_name + '_' + field.text.upper() + ': crate::Field = crate::Field::new({}, {}, {});\n'.format(str(int(msb.text)+1 - int(lsb.text)), lsb.text, register_name))
            lib.write('\n')
        lib.write('    }\n')
    lib.write('}\n\n')

    make_test(svd_root, lib)


def main():
    parser = argparse.ArgumentParser(description="Generate UTRA headers from SVD files")
    parser.add_argument(
        "-f", "--file", required=True, help="filename to process", type=str
    )
    parser.add_argument(
        "-o", "--output-lib", required=False, help="name of output Rust library", type=str, default="utra"
    )
    args = parser.parse_args()

    ifile = args.file

    generate(ifile, args.output_lib)

def make_test(root, lib):
    lib.write("""
#[cfg(test)]
mod tests{
    #[test]
    #[ignore]
    fn compile_check() {
        use super::*;
    \n""")
    peripherals = root.findall('.//peripherals/peripheral')
    for peripheral in peripherals:
        name = peripheral.find('name')
        peri_base = 'HW_' + name.text + '_BASE'
        registers = peripheral.find('registers')
        mod_name = name.text.lower()
        reg_name = name.text.lower() + '_csr'
        lib.write('        let mut {} = CSR::new({} as *mut u32);\n'.format(reg_name, peri_base))
        for register in registers:
            name = register.find('name')
            offset = register.find('addressOffset')
            register_name = name.text
            lib.write('        let foo = {}.r(utra::{}::{});\n'.format(reg_name, mod_name, register_name))
            lib.write('        {}.wo(utra::{}::{}, foo);\n'.format(reg_name, mod_name, register_name))
            for fields in register.find('fields'):
                field = fields.find('name')
                field_name = register_name + '_' + field.text.upper()
                lib.write('        let bar = {}.rf(utra::{}::{});\n'.format(reg_name, mod_name, field_name))
                lib.write('        {}.rmwf(utra::{}::{}, bar);\n'.format(reg_name, mod_name, field_name))
                lib.write('        let mut baz = {}.zf(utra::{}::{}, bar);\n'.format(reg_name, mod_name, field_name))
                lib.write('        baz |= {}.ms(utra::{}::{}, 1);\n'.format(reg_name, mod_name, field_name))
                lib.write('        {}.wfo(utra::{}::{}, baz);\n'.format(reg_name, mod_name, field_name))

            lib.write('\n')

    lib.write('    }\n')
    lib.write('}\n')


def make_toml(f, path):
    f.write("""
[package]
name = "utra"
version = "0.1.0"
authors = ["autogen by svd2utra.py", "Sean Cross <sean@xobs.io>", "bunnie <bunnie@kosagi.com>"]
homepage = "https://github.com/betrusted-io/utra"
description = "Register descriptions generated from {}"
edition = "2018"

# See more keys and their definitions at https://doc.rust-lang.org/cargo/reference/manifest.html

[dependencies]    
    """.format(path))

def add_header(f):
    f.write("""
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
    pub fn wfo(&mut self, field: Field, value: T) {
        let usize_base: *mut usize = unsafe { core::mem::transmute(self.base) };
        let value_as_usize: usize = (value.try_into().unwrap_or_default() & field.mask) << field.offset;
        unsafe {
            usize_base
                .add(field.register.offset)
                .write_volatile(value_as_usize)
        };
    }

    /// Write the entire contents of a register without reading it first
    pub fn wo(&mut self, reg: Register, value: T) {
        let usize_base: *mut usize = unsafe { core::mem::transmute(self.base) };
        let value_as_usize: usize = value.try_into().unwrap_or_default();
        unsafe { usize_base.add(reg.offset).write_volatile(value_as_usize) };
    }

    /// Zero a field from a provided value
    pub fn zf(&mut self, field: Field, value: T) -> T {
        let value_as_usize: usize = value.try_into().unwrap_or_default();
        (value_as_usize & !(field.mask << field.offset))
            .try_into()
            .unwrap_or_default()
         
    }
    
    /// Shift & mask a value to its final field position
    pub fn ms(&mut self, field: Field, value: T) -> T {
        let value_as_usize: usize = value.try_into().unwrap_or_default();
        ((value_as_usize & field.mask) << field.offset)
            .try_into()
            .unwrap_or_default()
    }

}
    """)
if __name__ == "__main__":
    main()
