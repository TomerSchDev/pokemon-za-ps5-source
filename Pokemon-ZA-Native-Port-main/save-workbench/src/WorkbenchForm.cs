using System.Text.Json;
namespace ZaSaveWorkbench;

public sealed class WorkbenchForm : Form {
    readonly Color ink=Color.FromArgb(229,236,245), muted=Color.FromArgb(162,178,195), panel=Color.FromArgb(25,36,51);
    readonly Label summary=new(){AutoSize=false,Dock=DockStyle.Fill,Padding=new Padding(18),TextAlign=ContentAlignment.TopRight};
    readonly Label source=new(){AutoSize=false,Height=44,Dock=DockStyle.Top,AutoEllipsis=true,Padding=new Padding(12)};
    readonly Label status=new(){Dock=DockStyle.Bottom,Height=40,Padding=new Padding(12),Text="מוכן · העבודה נעשית על עותקים בלבד"};
    readonly TabControl tabs=new(){Dock=DockStyle.Fill};
    readonly ComboBox locations=new(){Width=450,DropDownStyle=ComboBoxStyle.DropDownList,DisplayMember="Label"};
    readonly CheckBox crossMap=new(){Text="הצג גם מפות אחרות · ניסיוני, נדרשת בדיקה במשחק",AutoSize=true};
    readonly TextBox storySearch=new(){Width=350,PlaceholderText="סינון לפי שם / מפתח / קבוצה"};
    readonly TextBox compareText=new(){Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,WordWrap=false};
    readonly DataGridView party=Grid(),story=Grid();
    readonly NumericUpDown x=Number(),y=Number(),z=Number();
    readonly Label mapLabel=new(){Width=460,Height=32};
    readonly List<Bookmark> bookmarks=[];
    string? currentPath;SaveInfo? info;Bookmark? selectedBookmark;bool loading;

    static NumericUpDown Number()=>new(){Minimum=-100000,Maximum=100000,DecimalPlaces=9,Increment=.1M,Width=200};
    static DataGridView Grid()=>new(){Dock=DockStyle.Fill,ReadOnly=true,AllowUserToAddRows=false,AllowUserToDeleteRows=false,
        AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,SelectionMode=DataGridViewSelectionMode.FullRowSelect,
        RowHeadersVisible=false,BackgroundColor=Color.FromArgb(25,36,51),BorderStyle=BorderStyle.None};
    Button Button(string label,Action action,int width=190) {
        var b=new Button(){Text=label,Width=width,Height=38,FlatStyle=FlatStyle.Flat,BackColor=Color.FromArgb(44,70,83),ForeColor=ink,Margin=new Padding(6)};
        b.Click+=(_,_)=>Guard(action);return b;
    }
    FlowLayoutPanel Row(params Control[] controls) {var p=new FlowLayoutPanel(){Dock=DockStyle.Top,AutoSize=true,Padding=new Padding(8),FlowDirection=FlowDirection.RightToLeft};p.Controls.AddRange(controls);return p;}
    Label Note(string text,int height=70)=>new(){Text=text,Dock=DockStyle.Top,Height=height,Padding=new Padding(16),ForeColor=muted,TextAlign=ContentAlignment.MiddleRight};
    void Guard(Action action) {try{action();}catch(Exception ex){status.Text="הפעולה לא בוצעה";MessageBox.Show(this,ex.Message,"ZA Save Workbench",MessageBoxButtons.OK,MessageBoxIcon.Error);}}

    public WorkbenchForm(string? initial=null) {
        Text="ZA Save Workbench — מיקום ומחקר התקדמות";ClientSize=new Size(1100,760);MinimumSize=new Size(960,680);
        StartPosition=FormStartPosition.CenterScreen;BackColor=Color.FromArgb(15,24,36);ForeColor=ink;Font=new Font("Segoe UI",10);
        var heading=new Label(){Text="ZA Save Workbench",Dock=DockStyle.Top,Height=66,Font=new Font("Segoe UI",25,FontStyle.Bold),Padding=new Padding(18,12,0,0)};
        var buttons=Row(Button("פתיחת שמירה",ChooseSave),Button("יצירת סימניית מיקום",SaveBookmark),Button("טעינת סימנייה",LoadBookmark));
        Controls.Add(tabs);Controls.Add(source);Controls.Add(buttons);Controls.Add(heading);Controls.Add(status);
        BuildOverview();BuildLocation();BuildStory();BuildCompare();
        foreach(Control c in tabs.TabPages)Theme(c);
        status.BackColor=panel;
        LoadCatalogue();
        Shown+=(_,_)=>Guard(()=>{
            string candidate=initial??Path.Combine(AppContext.BaseDirectory,"assets","checkpoints","current","main");
            if(File.Exists(candidate))LoadSave(candidate);
        });
    }
    void Theme(Control c) {
        c.BackColor=panel;c.ForeColor=ink;
        if(c is DataGridView g) {
            g.EnableHeadersVisualStyles=false;g.ColumnHeadersDefaultCellStyle.BackColor=Color.FromArgb(44,70,83);g.ColumnHeadersDefaultCellStyle.ForeColor=ink;
            g.DefaultCellStyle.BackColor=panel;g.DefaultCellStyle.ForeColor=ink;g.DefaultCellStyle.SelectionBackColor=Color.FromArgb(51,91,105);
        }
        foreach(Control child in c.Controls)Theme(child);
    }
    void BuildOverview() {
        var page=new TabPage("השמירה שלי");var split=new TableLayoutPanel(){Dock=DockStyle.Fill,ColumnCount=1,RowCount=2};
        split.RowStyles.Add(new RowStyle(SizeType.Absolute,190));split.RowStyles.Add(new RowStyle(SizeType.Percent,100));split.Controls.Add(summary,0,0);split.Controls.Add(party,0,1);page.Controls.Add(split);tabs.TabPages.Add(page);
    }
    void BuildLocation() {
        var page=new TabPage("בחירת מיקום");var content=new FlowLayoutPanel(){Dock=DockStyle.Fill,FlowDirection=FlowDirection.TopDown,WrapContents=false,Padding=new Padding(24),AutoScroll=true};
        content.Controls.Add(new Label(){Text="בחר מיקום שנקרא משמירה קיימת, או ערוך קואורדינטות באותה מפה.",AutoSize=true,Margin=new Padding(0,10,0,18)});
        content.Controls.Add(crossMap);content.Controls.Add(locations);content.Controls.Add(mapLabel);
        foreach(var pair in new[]{("X",x),("Y",y),("Z · גובה",z)}) {
            var row=new FlowLayoutPanel(){Width=600,Height=50};row.Controls.Add(new Label(){Text=pair.Item1,Width=110,Padding=new Padding(0,8,0,0)});row.Controls.Add(pair.Item2);content.Controls.Add(row);
        }
        content.Controls.Add(new Label(){Text="שינוי מיקום בלבד: הקבוצה, החפצים, דגלי הסיפור ונתוני העולם נשמרים.\nמיקום אינו פותח אזור חסום או מסיים משימה. טעינת העותק במשחק עדיין דורשת בדיקה.",Width=900,Height=90,Margin=new Padding(0,18,0,0),ForeColor=muted});
        content.Controls.Add(Button("יצוא עותק עם המיקום",ExportMove,260));page.Controls.Add(content);tabs.TabPages.Add(page);
        locations.SelectedIndexChanged+=(_,_)=>{if(!loading&&locations.SelectedItem is Bookmark b)SelectLocation(b);};
        crossMap.CheckedChanged+=(_,_)=>Guard(()=>{if(currentPath!=null)LoadSave(currentPath);});
    }
    void BuildStory() {
        var page=new TabPage("מצב סיפור · קריאה");page.Controls.Add(story);page.Controls.Add(Row(storySearch));
        page.Controls.Add(Note("תצוגת מחקר לקריאה בלבד. הערכים מפוזרים בין כמה טבלאות; ערך phase אינו מספר משימה שאפשר להחליף באופן עצמאי.",70));tabs.TabPages.Add(page);
        storySearch.TextChanged+=(_,_)=>FilterStory();
    }
    void BuildCompare() {
        var page=new TabPage("השוואת שמירות");page.Controls.Add(compareText);page.Controls.Add(Row(Button("השוואה לשמירה אחרת",CompareSave,250)));tabs.TabPages.Add(page);
    }
    void LoadCatalogue() {
        var folder=Path.Combine(AppContext.BaseDirectory,"assets");
        var bm=Path.Combine(folder,"bookmarks.json");if(File.Exists(bm))bookmarks.AddRange(JsonSerializer.Deserialize<List<Bookmark>>(File.ReadAllText(bm),SaveEngine.Json)??[]);
    }
    void ChooseSave() {using var d=new OpenFileDialog(){Title="בחר קובץ main של Pokémon Legends: Z-A",Filter="Save files|main;*.sav;*.bin;*.backup|All files|*.*"};if(d.ShowDialog(this)==DialogResult.OK)LoadSave(d.FileName);}
    void LoadSave(string path) {
        var parsed=SaveEngine.Inspect(path);currentPath=Path.GetFullPath(path);info=parsed;
        source.Text=currentPath;
        string phase=parsed.Story.FirstOrDefault(x=>x.Name=="SYS_WORK_PHASE")?.Value??"לא ממופה";
        summary.Text=$"מאמן: {parsed.Trainer}    |    פוקימונים בקבוצה: {parsed.Party.Length}    |    כסף: {parsed.Money:N0}\r\n\r\nמפה: {parsed.Position.Map}    |    X: {parsed.Position.X:F3}    Y: {parsed.Position.Y:F3}    Z: {parsed.Position.Z:F3}\r\n\r\nמצב סיפור (phase): {phase}    |    פורמט שמירה: {parsed.Revision}\r\n\r\nהשמירה תקינה; קריאה וכתיבה ללא שינוי מחזירות קובץ זהה.";
        party.DataSource=parsed.Party;FilterStory();
        loading=true;locations.Items.Clear();locations.Items.Add(SaveEngine.Mark(currentPath,"המיקום הנוכחי"));
        foreach(var b in bookmarks.Where(x=>(crossMap.Checked||x.Position.Map==parsed.Position.Map)&&x.Revision==parsed.Revision&&x.Position!=parsed.Position))locations.Items.Add(b);
        locations.SelectedIndex=0;loading=false;if(locations.Items[0] is Bookmark first)SelectLocation(first);status.Text="השמירה נטענה · הקובץ המקורי לא השתנה";
    }
    void FilterStory() {string query=storySearch.Text.Trim();story.DataSource=info?.Story.Where(x=>$"{x.Group} {x.Name} {x.Key} {x.Value}".Contains(query,StringComparison.OrdinalIgnoreCase)).ToArray();}
    void SelectLocation(Bookmark b) {
        selectedBookmark=b;mapLabel.Text=$"Map: {b.Position.Map}    |    source phase: {b.Phase}";
        x.Value=Math.Clamp((decimal)b.Position.X,x.Minimum,x.Maximum);y.Value=Math.Clamp((decimal)b.Position.Y,y.Minimum,y.Maximum);z.Value=Math.Clamp((decimal)b.Position.Z,z.Minimum,z.Maximum);
    }
    void RequireSave() {if(currentPath==null||info==null)throw new InvalidOperationException("Open a save first.");}
    string? OutputFolder(string label) {using var d=new FolderBrowserDialog(){Description="בחר תיקיית יעד; תיווצר בה תיקייה חדשה לעותק"};return d.ShowDialog(this)==DialogResult.OK?Path.Combine(d.SelectedPath,label+"-"+DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")):null;}
    void ExportMove() {
        RequireSave();if(selectedBookmark==null)return;string? output=OutputFolder("ZA-Position");if(output==null)return;
        var target=selectedBookmark with {Position=selectedBookmark.Position with {X=(float)x.Value,Y=(float)y.Value,Z=(float)z.Value}};
        string result=SaveEngine.Move(currentPath!,output,target,crossMap.Checked);status.Text="נוצר עותק: "+result;
        MessageBox.Show(this,"נוצרו main חדש, גיבוי של המקור ודוח אימות.\n\n"+result,"היצוא הושלם");
    }
    void SaveBookmark() {
        RequireSave();using var d=new SaveFileDialog(){Filter="Position bookmark|*.json",FileName="ZA-position.json",OverwritePrompt=true};if(d.ShowDialog(this)!=DialogResult.OK)return;
        File.WriteAllText(d.FileName,JsonSerializer.Serialize(SaveEngine.Mark(currentPath!,Path.GetFileNameWithoutExtension(d.FileName)),SaveEngine.Json));status.Text="סימניית המיקום נשמרה";
    }
    void LoadBookmark() {
        using var d=new OpenFileDialog(){Filter="Position bookmark|*.json"};if(d.ShowDialog(this)!=DialogResult.OK)return;
        var b=JsonSerializer.Deserialize<Bookmark>(File.ReadAllText(d.FileName),SaveEngine.Json)??throw new InvalidDataException("Empty bookmark");SaveEngine.Validate(b.Position);bookmarks.Add(b);
        if(currentPath!=null)LoadSave(currentPath);status.Text="סימניית המיקום נוספה";
    }
    void CompareSave() {
        RequireSave();using var d=new OpenFileDialog(){Title="בחר שמירה להשוואה",Filter="Save files|main;*.sav;*.bin;*.backup|All files|*.*"};if(d.ShowDialog(this)!=DialogResult.OK)return;
        compareText.Text=JsonSerializer.Serialize(SaveEngine.Compare(currentPath!,d.FileName),SaveEngine.Json);status.Text="ההשוואה מוכנה · שתי השמירות נשארו ללא שינוי";
    }
}
