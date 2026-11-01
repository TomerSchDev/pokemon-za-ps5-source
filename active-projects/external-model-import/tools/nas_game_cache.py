from pathlib import Path
import gzip,pickle,mmap,os
import za_folder
from storage_paths import data_root

def install():
 base=za_folder.za_romfs.Game
 cache_path=data_root()/'qa/all-pokemon-20261030-r2/game-index.pickle.gz'
 class IndexedGame(base):
  def __init__(self,path):
   with gzip.open(cache_path,'rb') as stream:cache=pickle.load(stream)
   st=os.stat(path)
   assert st.st_size==cache['size'] and st.st_mtime_ns//100==cache['mtime_100ns'],'Game index cache is stale'
   self.f=open(path,'rb');self.m=mmap.mmap(self.f.fileno(),0,access=mmap.ACCESS_READ)
   self.entries=cache['entries'];self.files=cache['files'];self.packs=cache['packs'];self.pack_names=cache['pack_names'];self.oodle=za_folder.za_romfs.Oodle()
   start,size=self.entries['arc/data.trpfs'];self.pack=memoryview(self.m)[start:start+size];self.fb=za_folder.za_romfs.FB(self.pack)
 za_folder.za_romfs.Game=IndexedGame
 assert za_folder._game is None,'Install the cache before opening the game'
