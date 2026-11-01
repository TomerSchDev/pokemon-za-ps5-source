// za-common-words-1: 256 short English words authored locally for comparison identifiers.
// No external word list, network source or dictionary dependency was used.
// The order is protocol data: serialize each exact TitleCase UTF-8 word followed by LF.
// Its SHA-256 is pinned by WordBankSha256 in settings_codes.h and verified before use.
static constexpr const char* kComparisonWords[] = {
    "Amber", "Aqua", "Beige", "Black", "Blue", "Brown", "Coral", "Cream", "Gold", "Green", "Grey", "Orange", "Pink", "Purple", "Red", "White",
    "Bear", "Bee", "Bird", "Cat", "Cow", "Crab", "Deer", "Dog", "Dove", "Duck", "Fish", "Fox", "Frog", "Goat", "Hare", "Hawk",
    "Horse", "Koala", "Lamb", "Lion", "Llama", "Lynx", "Mole", "Moose", "Mouse", "Newt", "Otter", "Owl", "Panda", "Pig", "Pony", "Quail",
    "Rabbit", "Raven", "Robin", "Seal", "Shark", "Sheep", "Sloth", "Snail", "Snake", "Swan", "Tiger", "Toad", "Trout", "Turtle", "Whale", "Wolf",
    "Acorn", "Apple", "Aspen", "Bark", "Beach", "Birch", "Brook", "Bush", "Cedar", "Cliff", "Cloud", "Coast", "Creek", "Dune", "Earth", "Elm",
    "Fern", "Field", "Flame", "Flower", "Forest", "Frost", "Grass", "Grove", "Hill", "Ice", "Ivy", "Lake", "Leaf", "Meadow", "Moon", "Moss",
    "Oak", "Ocean", "Palm", "Pine", "Pond", "Rain", "Reed", "River", "Rock", "Root", "Rose", "Sand", "Sea", "Seed", "Shore", "Sky",
    "Snow", "Soil", "Spark", "Spring", "Star", "Stone", "Storm", "Stream", "Sun", "Thorn", "Tide", "Trail", "Tree", "Valley", "Wave", "Wind",
    "Almond", "Bagel", "Bean", "Berry", "Bread", "Bun", "Cake", "Candy", "Cheese", "Cherry", "Cocoa", "Corn", "Date", "Fig", "Flour", "Fruit",
    "Grape", "Honey", "Jam", "Juice", "Lemon", "Lime", "Mango", "Melon", "Mint", "Nut", "Olive", "Onion", "Peach", "Pear", "Plum", "Rice",
    "Arrow", "Ball", "Basket", "Bell", "Belt", "Bench", "Book", "Bowl", "Box", "Brush", "Bucket", "Button", "Cabin", "Candle", "Cap", "Card",
    "Chair", "Clock", "Coin", "Comb", "Crown", "Cube", "Cup", "Door", "Drum", "Flag", "Flute", "Fork", "Frame", "Glass", "Globe", "Hammer",
    "Hat", "House", "Jar", "Key", "Kite", "Lamp", "Lantern", "Map", "Mask", "Medal", "Mirror", "Needle", "Nest", "Note", "Paint", "Pen",
    "Piano", "Pillow", "Pin", "Plate", "Pot", "Ring", "Rope", "Rug", "Sail", "Scarf", "Shell", "Shoe", "Spoon", "Stamp", "Stool", "Tent",
    "Brave", "Bright", "Calm", "Clear", "Cool", "Cozy", "Crisp", "Daring", "Fair", "Fancy", "Fast", "Fresh", "Gentle", "Happy", "Kind", "Lucky",
    "Merry", "Neat", "Nice", "Plain", "Proud", "Quick", "Quiet", "Round", "Sharp", "Shiny", "Soft", "Solid", "Still", "Sweet", "Warm", "Young",
};
