using PKHeX.Core;
using System.Security.Cryptography;
using System.Text.Json;
static SAV9ZA Read(string p){var b=File.ReadAllBytes(p);if(!SwishCrypto.GetIsHashValid(b))throw new InvalidDataException("Save hash invalid");return new SAV9ZA(b);}
static string Hash(string p)=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(p))).ToLowerInvariant();
var mode=args[0];var before=Read(args[1]);
if(mode=="inspect"){
 var rows=Enumerable.Range(0,3000).Select(i=>before.Items.GetItem((ushort)i)).Where(i=>i.Count>0).Select(i=>new{id=i.Index,count=i.Count,pouch=i.Pouch});
 Console.WriteLine(JsonSerializer.Serialize(new{hash_valid=true,money=before.Money,items=rows},new JsonSerializerOptions{WriteIndented=true}));return;
}
var after=Read(args[2]);
if(mode=="one"){
 ushort id=ushort.Parse(args[3]);int expected=int.Parse(args[4]);var item=after.Items.GetItem(id);
 if(item.Count!=expected)throw new InvalidDataException($"Item {id}: {item.Count} != {expected}");
 for(ushort i=0;i<3000;++i)if(i!=id&&before.Items.GetItemQuantity(i)!=after.Items.GetItemQuantity(i))throw new InvalidDataException($"Unrequested count changed {i}");
 if(before.Money!=after.Money)throw new InvalidDataException("Money changed");
 if(!Enumerable.Range(0,after.PartyCount).All(i=>after.GetPartySlotAtIndex(i).ChecksumValid))throw new InvalidDataException("Party checksum invalid");
 Console.WriteLine(JsonSerializer.Serialize(new{hash_valid=true,party_checksums_valid=true,id,before=before.Items.GetItemQuantity(id),after=item.Count,expected,pocket=item.Pouch,unrequested_counts_unchanged=true,money_unchanged=true,before_sha256=Hash(args[1]),after_sha256=Hash(args[2])},new JsonSerializerOptions{WriteIndented=true}));return;
}
var catalog=JsonDocument.Parse(File.ReadAllText(args[3])).RootElement.EnumerateArray().Select(j=>(id:j.GetProperty("id").GetInt32(),cap:j.GetProperty("cap").GetInt32(),pocket:j.GetProperty("pocket").GetInt32())).ToArray();
var allowed=catalog.Select(i=>i.id).ToHashSet();
var result=catalog.Select(i=>{
 var a=after.Items.GetItem((ushort)i.id);var b=before.Items.GetItem((ushort)i.id);
 if(a.Count!=i.cap||a.Pouch!=i.pocket)throw new InvalidDataException($"Item {i.id}: {a.Count}/{a.Pouch}, expected {i.cap}/{i.pocket}");
 return new{id=i.id,before=b.Count,after=a.Count,pocket=a.Pouch,cap=i.cap};
}).ToArray();
for(ushort i=0;i<3000;++i){if(allowed.Contains(i))continue;var b=before.Items.GetItem(i);var a=after.Items.GetItem(i);if(a.Count!=b.Count||a.Pouch!=b.Pouch||(a.Flags&~5u)!=(b.Flags&~5u))throw new InvalidDataException($"Unrequested item changed {i}");}
if(before.Money!=after.Money)throw new InvalidDataException("Money changed");
var partyValid=Enumerable.Range(0,after.PartyCount).All(i=>after.GetPartySlotAtIndex(i).ChecksumValid);
if(!partyValid)throw new InvalidDataException("Party checksum invalid");
var changed=after.AllBlocks.Where(b=>!before.AllBlocks.Single(x=>x.Key==b.Key).Data.SequenceEqual(b.Data)).Select(b=>b.Key.ToString("X8")).ToArray();
if(mode=="unchanged"&&!before.AllBlocks.Single(b=>b.Key==0x21C9BD44).Data.SequenceEqual(after.AllBlocks.Single(b=>b.Key==0x21C9BD44).Data))throw new InvalidDataException("Inventory changed on capped reload");
Console.WriteLine(JsonSerializer.Serialize(new{hash_valid=true,party_checksums_valid=partyValid,unrequested_inventory_unchanged=true,money_unchanged=true,count=result.Length,items=result,changed_blocks=changed,before_sha256=Hash(args[1]),after_sha256=Hash(args[2])},new JsonSerializerOptions{WriteIndented=true}));
