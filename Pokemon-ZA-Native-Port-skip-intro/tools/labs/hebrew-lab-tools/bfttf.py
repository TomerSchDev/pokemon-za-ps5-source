"""Nintendo .bfttf / .bfotf font containers: 4-byte magic, u32 big-endian size XOR key, then the sfnt XOR key
(the key 49 62 18 06 repeated). Same scheme as pokeza-recomp runtime/hle/pl.c and tools/za/prompt_textures.py."""
KEY = bytes([0x49, 0x62, 0x18, 0x06])


def decode(d):
    n = int.from_bytes(bytes(a ^ b for a, b in zip(d[4:8], KEY)), 'big')
    return bytes(d[8 + i] ^ KEY[i % 4] for i in range(n))


def encode(magic, sfnt):
    t = sfnt + b'\0' * (-len(sfnt) % 4)
    size = bytes(a ^ b for a, b in zip(len(t).to_bytes(4, 'big'), KEY))
    key = (KEY * (len(t) // 4 + 1))[:len(t)]
    return magic + size + bytes(a ^ b for a, b in zip(t, key))
