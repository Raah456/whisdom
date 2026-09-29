"""MSB-first bit reader. Game-agnostic: many replay formats are bit-packed."""
class BitStream:
    def __init__(self, data, offset=0):
        self.d=data; self.ro=offset; self.nbits=len(data)*8
    def bits(self,c):
        if self.ro+c>self.nbits: raise IndexError("end of stream")
        r=0
        while c:
            byte=self.d[self.ro>>3]; bit=self.ro&7; rem=8-bit
            take=c if c<rem else rem
            r|=((byte&((1<<rem)-1))>>(rem-take))<<(c-take)
            c-=take; self.ro+=take
        return r
    def u32(self): return self.bits(32)
    def u16(self): return self.bits(16)
    def bit(self):  return self.bits(1)!=0
    def string(self):
        n=self.u16()
        return bytes(self.bits(8) for _ in range(n)).decode("utf-8","replace")
