"""Encoder menu selection state."""
class select_t:
    def __init__(self):
        self.now = 0
        self.last = 0

    def set(self, v):
        self.now = self.last = v

    def reset(self):
        self.set(0)

    def changed(self):
        c = (self.now != self.last)
        if c:
            self.last = self.now
            return c

    def dec(self):
        if (self.now):
            self.now = max(0,self.now-getattr(self,"batch_steps",1))
        return self.changed()

    def inc(self, v):
        if (self.now < (v - 1)):
            self.now = min(v-1,self.now+getattr(self,"batch_steps",1))
        else:
            self.now = (v - 1)
        return self.changed()

