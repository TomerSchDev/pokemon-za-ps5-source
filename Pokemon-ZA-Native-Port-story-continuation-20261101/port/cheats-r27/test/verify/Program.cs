using PKHeX.Core;
using System.Security.Cryptography;
using System.Text.Json;
static SAV9ZA Read(string path) {
    var raw=File.ReadAllBytes(path);
    if(!SwishCrypto.GetIsHashValid(raw)) throw new InvalidDataException("Invalid save hash");
    return new SAV9ZA(raw);
}
static string Hash(string path)=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
var mode=args[0];var before=Read(args[1]);
if(mode=="near-cap") {
    if(File.Exists(args[2])) throw new IOException("Refusing to overwrite test fixture");
    before.Money=9999990;File.WriteAllBytes(args[2],before.Write().ToArray());
    Console.WriteLine(JsonSerializer.Serialize(new {fixture=args[2],money=Read(args[2]).Money,sha256=Hash(args[2])}));
} else if(mode=="verify") {
    var after=Read(args[2]);var expected=uint.Parse(args[3]);
    if(after.Money!=expected)throw new InvalidDataException($"Money {after.Money} != {expected}");
    var changes=after.AllBlocks.Where(b=>!before.AllBlocks.Single(x=>x.Key==b.Key).Data.SequenceEqual(b.Data)).Select(b=>b.Key.ToString("X8")).ToArray();
    var goodPokemon=Enumerable.Range(0,after.PartyCount).All(i=>after.GetPartySlotAtIndex(i).ChecksumValid);
    if(!goodPokemon)throw new InvalidDataException("Party checksum invalid");
    Console.WriteLine(JsonSerializer.Serialize(new {before_money=before.Money,after_money=after.Money,expected_money=expected,
      hash_valid=true,party_checksums_valid=goodPokemon,changed_blocks=changes,before_sha256=Hash(args[1]),after_sha256=Hash(args[2])},new JsonSerializerOptions{WriteIndented=true}));
} else throw new ArgumentException("Expected near-cap or verify");
