using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using PKHeX.Core;

public static class InspectFiftySave {
 public static void Run(string path) {
  var raw=File.ReadAllBytes(path);
  if(!SwishCrypto.GetIsHashValid(raw))throw new InvalidDataException("Invalid source save hash");
  var sav=new SAV9ZA(raw.ToArray());
  var party=Enumerable.Range(0,sav.PartyCount).Select(i=>{
   var p=(PA9)sav.GetPartySlotAtIndex(i);
   return new {slot=i,species=p.Species,internalSpecies=p.SpeciesInternal,level=p.CurrentLevel,
    moves=new[]{p.Move1,p.Move2,p.Move3,p.Move4},pp=new[]{p.Move1_PP,p.Move2_PP,p.Move3_PP,p.Move4_PP},
    p.ChecksumValid,p.Status_Condition,p.IsEgg,p.Stat_HPCurrent,p.ObedienceLevel,p.MetLevel};
  }).ToArray();
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(path)))throw new InvalidDataException("Source changed during inspection");
  Console.WriteLine(JsonSerializer.Serialize(new {path,party,party_count=sav.PartyCount,
   candy=sav.Items.GetItemQuantity(50),other_pouch_unlocked=sav.Items.UnlockedOther}));
 }
}

public static class PreparedSpeciesFixture {
 public static void Run(string source,string output,ushort national,ushort internalSpecies,byte level,ushort move1,ushort move2) {
  if(File.Exists(output))throw new IOException("Use a new private fixture version");
  if(level<1||level>100||national<1||national>1025||move1==0||move2==0)throw new ArgumentOutOfRangeException("Fixture inputs");
  var raw=File.ReadAllBytes(source);
  if(!SwishCrypto.GetIsHashValid(raw))throw new InvalidDataException("Invalid source save");
  var sav=new SAV9ZA(raw.ToArray());var before=sav.AllBlocks.ToDictionary(b=>b.Key,b=>b.Data.ToArray());
  var p=(PA9)sav.GetPartySlotAtIndex(0).Clone();
  p.Species=national;p.Form=0;
  if(p.SpeciesInternal!=internalSpecies)throw new InvalidDataException("National/internal mapping differs from current PKHeX");
  p.PID+=0x500;p.EncryptionConstant+=0x500;
  if(p.IsShiny)p.PID^=0x10000000;
  p.Gender=p.PersonalInfo.Gender==255?(byte)2:p.PersonalInfo.Gender==254?(byte)1:(byte)0;
  p.Nickname=GameInfo.Strings.Species[national];p.IsNicknamed=false;p.HeldItem=0;p.IsEgg=false;p.Status_Condition=0;
  p.MetLevel=1;p.ObedienceLevel=1;p.CurrentLevel=level;p.CurrentFriendship=70;
  p.Move1=move1;p.Move2=move2;p.Move3=0;p.Move4=0;
  p.Move1_PPUps=0;p.Move2_PPUps=0;p.Move3_PPUps=0;p.Move4_PPUps=0;
  p.RelearnMove1=move1;p.RelearnMove2=move2;p.RelearnMove3=0;p.RelearnMove4=0;
  p.ClearMovePlusFlags();p.ClearMoveRecordFlags();p.HealPP();p.ResetPartyStats();p.RefreshChecksum();
  sav.SetPartySlotAtIndex(p,0);sav.PartyCount=1;
  // Fixture generation is not a catch. Keep the source Pokedex byte-identical.
  sav.AllBlocks.Single(b=>b.Key==0x2D87BE5C).ChangeData(before[0x2D87BE5C]);
  sav.Items.SetItemQuantity(50,999);sav.Items.UnlockedMedicine=true;sav.Items.UnlockedOther=true;
  var bytes=sav.Write().ToArray();var check=new SAV9ZA(bytes.ToArray());var primary=(PA9)check.GetPartySlotAtIndex(0);
  var changed=check.AllBlocks.Where(b=>!before[b.Key].AsSpan().SequenceEqual(b.Data)).Select(b=>b.Key).ToArray();
  var allowed=new uint[]{0x3AA1A9AD,0x21C9BD44,0x0D66012C};
  if(changed.Any(k=>!allowed.Contains(k)))throw new InvalidDataException("Unexpected block change: "+string.Join(",",changed.Select(k=>k.ToString("X8"))));
  if(!SwishCrypto.GetIsHashValid(bytes)||!primary.ChecksumValid||primary.Species!=national||primary.CurrentLevel!=level||primary.Move1!=move1||primary.Move2!=move2||primary.Stat_HPCurrent==0||check.PartyCount!=1||check.Items.GetItemQuantity(50)!=999||!check.Items.UnlockedOther)throw new InvalidDataException("Round-trip fixture assertions failed");
  if(!raw.AsSpan().SequenceEqual(File.ReadAllBytes(source)))throw new InvalidDataException("Source save changed");
  Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);File.WriteAllBytes(output,bytes);
  Console.WriteLine(JsonSerializer.Serialize(new {test_clone_only=true,original_save_unchanged=true,species=primary.Species,internalSpecies=primary.SpeciesInternal,level=primary.CurrentLevel,candy=999,changed_blocks=changed.Select(k=>k.ToString("X8")).ToArray()}));
 }
}
