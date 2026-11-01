using System.Text.Json;
namespace ZaSaveWorkbench;
internal static class Program {
    [STAThread]
    static int Main(string[] args) {
        if(args.Length>0&&args[0]!="--gui") {
            try {
                object result=args[0] switch {
                    "inspect" when args.Length==2=>SaveEngine.Inspect(args[1]),
                    "bookmark" when args.Length==3=>SaveEngine.Mark(args[1],args[2]),
                    "move" when args.Length==4=>SaveEngine.Move(args[1],args[2],JsonSerializer.Deserialize<Bookmark>(File.ReadAllText(args[3]),SaveEngine.Json)??throw new InvalidDataException()),
                    "move" when args.Length==5&&args[4]=="--experimental-map"=>SaveEngine.Move(args[1],args[2],JsonSerializer.Deserialize<Bookmark>(File.ReadAllText(args[3]),SaveEngine.Json)??throw new InvalidDataException(),true),
                    "compare" when args.Length==3=>SaveEngine.Compare(args[1],args[2]),
                    _=>throw new ArgumentException("inspect SAVE | bookmark SAVE LABEL | move SAVE NEW_FOLDER BOOKMARK_JSON [--experimental-map] | compare SAVE SAVE")
                };
                Console.WriteLine(JsonSerializer.Serialize(result,SaveEngine.Json));return 0;
            } catch(Exception e) {Console.WriteLine(JsonSerializer.Serialize(new {Error=e.Message}));return 2;}
        }
        ApplicationConfiguration.Initialize();Application.Run(new WorkbenchForm(args.Skip(1).FirstOrDefault()));return 0;
    }
}
