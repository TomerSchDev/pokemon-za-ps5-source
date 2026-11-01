"""Idle-only r21b observer-maintenance update; rendering runtime remains r21."""
import deploy
t=deploy.t
t.SOURCE=deploy.ROOT/'artifacts/randomizer-r21b-preparation/PPSA91762/eboot.bin'
t.BASE=deploy.ROOT/'artifacts/randomizer-r21-preparation/PPSA91762/eboot.bin'
t.BASE_SHA='75b2b33119e333f2f5b0f203719befc686b14d64a5e1cbb7d6932931e9eb3dad'
t.E=deploy.ROOT/'evidence/preparation-r21-hardware/deployment-r21b'
if __name__=='__main__':t.main()
