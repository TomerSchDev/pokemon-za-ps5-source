"""Idle-only r23 slot-depth experiment; restore exact r22 if needed."""
import deploy

t=deploy.t
t.SOURCE=deploy.ROOT/'artifacts/randomizer-r23-slot-depth/PPSA91762/eboot.bin'
t.BASE=deploy.ROOT/'artifacts/randomizer-r22-immutable-spans/PPSA91762/eboot.bin'
t.BASE_SHA='1d7695a2ba23036e70448e11a2fb27fd48c13bbb6545816677ca877c1e56ca83'
t.E=deploy.ROOT/'evidence/preparation-r21-hardware/deployment-r23'
if __name__=='__main__':t.main()
