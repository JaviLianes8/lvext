# lvext

Pack and unpack LabVIEW/x87 80-bit extended-precision floats in pure Python

## Install

```
pip install lvext
```

## Usage

```python
from lvext import pack_ext, unpack_ext, pack_ext128, unpack_ext128

# LabVIEW flattens Extended (EXT) as 10 big-endian bytes.
data = pack_ext(1.0)
assert data == bytes.fromhex("3fff8000000000000000")
assert unpack_ext(data) == 1.0

# x87 memory is little-endian; pass the byte order you need.
assert unpack_ext(pack_ext(-0.5, "little"), "little") == -0.5

# The 16-byte padded storage form keeps the value in the low 80 bits.
assert unpack_ext128(pack_ext128(1234.5)) == 1234.5
```

Sign, the 15-bit exponent (bias 16383), the explicit 64-bit mantissa, signed
zero, subnormals, infinities and NaN are all handled. A Python float is a 64-bit
double, so a round trip is exact for every value a double can represent; values
outside the double range saturate to infinity, and values below it underflow to
zero.

## Why

LabVIEW stores and flattens its Extended type as an 80-bit (or 128-bit padded)
x87 float, and the standard library cannot touch it: `struct` has no 80-bit
format, and `numpy.longdouble` is platform-dependent and is usually just a 64-bit
double on Windows and MSVC, so it cannot read the extra bits. There was no
portable package for this. `lvext` does the bit math in pure Python with no
dependencies, so the same bytes decode identically on every platform.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
