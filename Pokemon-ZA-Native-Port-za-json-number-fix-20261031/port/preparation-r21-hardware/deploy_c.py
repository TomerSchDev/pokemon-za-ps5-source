"""Idle-only r21c native filesystem adapter; rendering runtime remains r21."""
import deploy
t=deploy.t
t.SOURCE=deploy.ROOT/'artifacts/randomizer-r21c-preparation/PPSA91762/eboot.bin'
t.BASE=deploy.ROOT/'artifacts/randomizer-r21b-preparation/PPSA91762/eboot.bin'
t.BASE_SHA='1bc9a8bfef84b8a8c08dbaf0c04a5dbb13e1d555e2c77332e57fc82395c3910c'
t.E=deploy.ROOT/'evidence/preparation-r21-hardware/deployment-r21c'
if __name__=='__main__':t.main()
