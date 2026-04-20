# Mansion Image Generation Prompts

Prompts for generating illustrations for the Clue board game.

> **Allowed aspect ratios:** 1:1, 2:3, 4:5, 9:16, 16:9, 5:4, 3:2

---

## Characters

Character portrait illustrations. Each depicts the suspect in a dramatic three-quarter pose with distinct personality and color identity.

---

### Miss Scarlett

**Ratio:** 2:3

> Colored pencil art. Dark victorian noir Cluedo suspect portrait — Miss Scarlett. A striking young woman in a figure-hugging scarlet evening gown with black lace trim. Fiery red lips and sharp, knowing eyes. Deep crimson and black tones. A cigarette holder in one gloved hand, a small pearl-handled clutch in the other. Diamond earrings catching the light. Moonlit balcony behind her with billowing curtains. Confident, dangerous, seductive.

---

### Colonel Mustard

**Ratio:** 2:3

> Colored pencil art. Dark victorian noir Cluedo suspect portrait — Colonel Mustard. A broad-shouldered older military man in a mustard-yellow dress uniform with brass buttons and medal ribbons. Thick grey moustache, weathered tan face, steely eyes. Golden ochre and military khaki tones. A riding crop tucked under one arm, a brandy snifter in hand. Trophy room background with crossed sabres on the wall. Warm lamplight from a desk. Imperious, proud, guarded.

---

### Mrs. White

**Ratio:** 2:3

> Colored pencil art. Dark victorian noir Cluedo suspect portrait — Mrs. White. A young woman in her late twenties with fiery red hair pinned up in a loose, slightly rebellious updo, stray curls framing her face. Bright green eyes with a mischievous glint. Wearing a crisp white blouse with rolled sleeves and a dark apron, as if she's been busy and doesn't care who knows it. Warm ivory and burnt sienna tones. A feather duster in one hand held like a fencing foil, a ring of manor keys at her hip. Kitchen doorway behind her, warm gaslight catching the copper pots. Spirited, sharp-witted, underestimated.

---

### Reverend Green

**Ratio:** 2:3

> Colored pencil art. Dark victorian noir Cluedo suspect portrait — Reverend Green. A handsome, sharp-jawed man in his mid-thirties wearing a tailored dark green clerical suit with a white dog collar, the fit just a little too fashionable for a real clergyman. Warm brown eyes with a rakish glint, thick dark hair swept back with effortless style, a disarming smile that could sell you anything. Deep emerald and charcoal tones. One hand resting casually on a leather-bound bible he's clearly never read, the other adjusting gold cufflinks that no reverend could afford. Candlelit parlour behind him with velvet curtains and a half-empty champagne flute on the mantel. Charming, confident, dangerously likeable.

---

### Mrs. Peacock

**Ratio:** 2:3

> Colored pencil art. Dark victorian noir Cluedo suspect portrait — Mrs. Peacock. A regal woman in an elaborate royal blue gown with a peacock-feather brooch at the collar. Hair in a perfect chignon, sharp aristocratic features, an icy stare. Sapphire blue and midnight indigo tones. A folded silk fan in one hand, the other resting on the back of a gilded chair. Grand parlour background with oil paintings and velvet drapes. Warm candlelight through a leaded window. Commanding, haughty, calculating.

---

### Professor Plum

**Ratio:** 2:3

> Colored pencil art. Dark victorian noir Cluedo suspect portrait — Professor Plum. A disheveled middle-aged academic in a rumpled plum-purple tweed jacket with leather elbow patches. Wild salt-and-pepper hair, round tortoiseshell glasses slightly askew, distracted expression. Rich violet and dusty aubergine tones. An open notebook crammed with equations in one hand, a pipe trailing smoke in the other. University study background with chalkboard scrawl and teetering book stacks. Warm lamplight through a dormer window. Brilliant, absent-minded, oddly suspicious.

---

## Rooms — Night (Dark Mode)

The original nighttime room illustrations. Used for the **dark** theme.

> **Approach A — Separate images:** Generate these night prompts for dark mode and the daytime prompts below for light mode. Store night images in `frontend/public/images/clue/rooms/night/` and day images in `frontend/public/images/clue/rooms/day/` (served at `/images/clue/rooms/night/...` and `/images/clue/rooms/day/...`).
>
> **Approach B — Night CSS filter over daytime base:** Generate *only* the daytime prompts below, then apply a CSS night filter in dark mode:
> ```css
> filter: brightness(0.55) saturate(0.7) sepia(0.15) hue-rotate(-10deg);
> ```
> This avoids maintaining two image sets. The base daytime images in `frontend/public/images/clue/rooms/day/` are used as-is in light mode (via `/images/clue/rooms/day/...`) and filtered for dark mode.

---

### Study

**Ratio:** 16:9

> Colored pencil art. Dark victorian noir of a Cluedo mansion — the Study. Top view from the bottom, nighttime, moonlight streaming through tall windows on the top wall and left wall. Deep midnight blue and mahogany tones. A heavy oak desk strewn with papers and an inkwell, floor-to-ceiling bookshelves, a globe in the corner, a green banker's lamp casting a small circle of light. Persian rug over dark hardwood. Secret passage trapdoor barely visible beneath the rug.

---

### Hall

**Ratio:** 4:5

> Colored pencil art. Grand victorian Cluedo mansion — the Hall. Top view from the bottom, nighttime, warm gaslight glow throughout. Warm amber and ivory tones. Black-and-white checkerboard marble floor, ornate chandelier shadow cast from above, grand double entry doors at the far wall, a tall grandfather clock, coat rack with a top hat and cane. Sconces light the wallpapered walls. No windows.

---

### Lounge

**Ratio:** 5:4

> Colored pencil art. Moody victorian Cluedo mansion — the Lounge. Top view from the bottom, nighttime, pale moonlight filtering through heavy drapes on the top wall and right wall. Rich crimson and gold tones. Tufted velvet chaise longue, a crackling fireplace with marble mantel, crystal decanter and glasses on a side table, thick burgundy drapes, an animal-skin rug.

---

### Library

**Ratio:** 3:2

> Colored pencil art. Atmospheric victorian Cluedo mansion — the Library. Top view from the bottom, nighttime, cold moonlight casting long shadows through bay windows on the left wall. Door on the right wall. Forest green and aged leather tones. Towering shelves packed with leather-bound volumes, a rolling ladder against one wall, a reading chair with an open book face-down on the armrest, a brass telescope near the window, scattered notes and a magnifying glass on a side table.

---

### Billiard Room

**Ratio:** 5:4

> Colored pencil art. Smoky victorian Cluedo mansion — the Billiard Room. Top view from the bottom/south, nighttime, a sliver of moonlight through tall windows on the left wall. Door on the back wall on the left side. Emerald green and polished walnut tones. A full-size billiard table with balls mid-game, cue rack on the wall, low-hanging tiffany lamp over the table, leather wingback chairs, a whiskey cart, mounted trophy heads faintly visible on wood-paneled walls.

---

### Dining Room

**Ratio:** 1:1

> Colored pencil art. Opulent victorian Cluedo mansion — the Dining Room. Top view from the bottom, nighttime, soft moonlight spilling across the table through tall windows on the right wall. Deep plum and silver tones. A long mahogany dining table set for six with fine china and candelabras, high-backed chairs, a sideboard with a silver tureen, wine bottles, and a carving knife. Heavy damask curtains. Spilled red wine on the white tablecloth.

---

### Conservatory

**Ratio:** 5:4

> Colored pencil art. Lush victorian Cluedo mansion — the Conservatory. Top view from the bottom/south, nighttime, moonlight flooding through tall windows on the left wall and glass panes behind the camera. Door on the back wall on the right side. Warm sage green and terracotta tones. Potted palms and exotic ferns, a wrought-iron garden bench, stone tile floor with moss in the cracks, a watering can, scattered gardening tools, and a vine creeping along the window frame.

---

### Ballroom

**Ratio:** 1:1

> Colored pencil art. Elegant victorian Cluedo mansion — the Ballroom. Top view from the bottom, nighttime, warm gaslight washing across the dance floor. Lavender and champagne gold tones. Vast polished parquet dance floor with geometric inlay pattern, a grand piano in the corner, enormous crystal chandelier reflection on the floor, floor-length mirrors on the walls, velvet rope barriers, a single dropped silk glove. No windows.

---

### Kitchen

**Ratio:** 1:1

> Colored pencil art. Rustic victorian Cluedo mansion — the Kitchen. Top view from the bottom, nighttime, soft moonlight through windows on the right wall. Warm copper and cream tones. A heavy butcher-block island, cast-iron pots hanging from a ceiling rack, a coal-burning range with a kettle, flour dusted across the counter, a knife block, bundles of dried herbs, a pantry door slightly ajar, an open toolbox on the floor with a wrench-shaped gap in the tray. Warm gaslight glow on stone floor tiles.

---

### Grand Staircase — Night

**Ratio:** 4:5

> Colored pencil art. Dramatic victorian Cluedo mansion — the Grand Staircase. Top view from the bottom, nighttime, warm gaslight from wall sconces illuminating a wide, straight staircase in grand ballroom style. Rich mahogany and deep burgundy tones. A long central flight with symmetrical carved banisters and a plush crimson runner rises directly to an opulent landing. Crystal chandeliers glint above while oil portraits of stern ancestors line the walls. A suit of armor stands guard at the landing. Polished brass handrails reflect the gaslight against dark wood paneling and a heavy newel post topped with a carved finial.

---

## Rooms — Day (Light Mode)

Daytime versions of the same rooms. Same furniture, same composition, but bright natural daylight instead of moonlit noir. These serve as the **light** theme images and as the base for the CSS night-filter approach.

Images go in `frontend/public/images/clue/rooms/day/` (full) and `frontend/public/images/clue/rooms/day/thumbnails/` (thumbs).

---

### Study — Day

**Ratio:** 16:9

> Colored pencil art. Bright victorian Cluedo mansion — the Study. Top view from the bottom, daytime, warm afternoon sunlight streaming through tall windows on the top wall and left wall, casting golden rectangles across the floor. Rich mahogany and warm honey tones. A heavy oak desk strewn with papers and an inkwell, floor-to-ceiling bookshelves, a globe in the corner, a green banker's lamp (unlit). Persian rug over sun-warmed hardwood. Secret passage trapdoor barely visible beneath the rug. Dust motes floating in the sunbeams.

---

### Hall — Day

**Ratio:** 4:5

> Colored pencil art. Grand victorian Cluedo mansion — the Hall. Top view from the bottom, daytime, bright warm light from the chandelier and open doors at the far wall letting daylight flood in. Warm ivory and cream tones. Black-and-white checkerboard marble floor gleaming with polish, ornate crystal chandelier sparkling above, grand double entry doors standing open revealing a sun-drenched garden beyond, a tall grandfather clock, coat rack with a top hat and cane. Sconces unlit against sunlit wallpapered walls.

---

### Lounge — Day

**Ratio:** 5:4

> Colored pencil art. Warm victorian Cluedo mansion — the Lounge. Top view from the bottom, daytime, golden afternoon sunlight pouring through parted drapes on the top wall and right wall, painting warm stripes across the carpet. Rich crimson and warm gold tones. Tufted velvet chaise longue bathed in light, a fireplace with marble mantel (fire out, neatly set), crystal decanter and glasses catching the sun on a side table, thick burgundy drapes pulled back with tasselled ties, an animal-skin rug with soft shadow patterns.

---

### Library — Day

**Ratio:** 3:2

> Colored pencil art. Sunlit victorian Cluedo mansion — the Library. Top view from the bottom, daytime, warm golden light streaming through bay windows on the left wall, illuminating dust motes and leather spines. Door on the right wall. Forest green and warm amber-leather tones. Towering shelves packed with leather-bound volumes glowing in the light, a rolling ladder against one wall, a reading chair with an open book face-down on the armrest, a brass telescope near the bright window, scattered notes and a magnifying glass on a sun-dappled side table.

---

### Billiard Room — Day

**Ratio:** 5:4

> Colored pencil art. Bright victorian Cluedo mansion — the Billiard Room. Top view from the bottom/south, daytime, warm afternoon light streaming through tall windows on the left wall, illuminating the green baize. Door on the back wall on the left side. Emerald green and polished walnut tones. A full-size billiard table with balls mid-game catching the light, cue rack on the wall, tiffany lamp (unlit) over the table, leather wingback chairs in dappled sun, a whiskey cart, mounted trophy heads clearly visible on sun-washed wood-paneled walls.

---

### Dining Room — Day

**Ratio:** 1:1

> Colored pencil art. Bright victorian Cluedo mansion — the Dining Room. Top view from the bottom, daytime, warm sunlight flooding across the table through tall windows on the right wall, white tablecloth glowing. Warm plum and bright silver tones. A long mahogany dining table set for six with fine china and candelabras (unlit), high-backed chairs casting crisp shadows, a sideboard with a silver tureen, wine bottles, and a carving knife. Damask curtains pulled wide. Spilled red wine vivid on the white tablecloth.

---

### Conservatory — Day

**Ratio:** 5:4

> Colored pencil art. Sun-drenched victorian Cluedo mansion — the Conservatory. Top view from the bottom/south, daytime, brilliant sunlight flooding through tall windows on the left wall and glass panes behind the camera, filling the room with warm green-gold light. Door on the back wall on the right side. Vibrant sage green and warm terracotta tones. Potted palms and exotic ferns lush in the sunlight, a wrought-iron garden bench with dappled shadows, stone tile floor with moss glowing green in the cracks, a watering can, scattered gardening tools, and a vine creeping along the bright window frame.

---

### Ballroom — Day

**Ratio:** 1:1

> Colored pencil art. Radiant victorian Cluedo mansion — the Ballroom. Top view from the bottom, daytime, bright chandelier light and ambient daylight washing across the dance floor. Warm lavender and champagne gold tones. Vast polished parquet dance floor with geometric inlay pattern gleaming, a grand piano in the corner, enormous crystal chandelier sparkling brilliantly, floor-length mirrors reflecting bright light, velvet rope barriers, a single dropped silk glove. No windows — lit by brilliant chandelier and open doors.

---

### Kitchen — Day

**Ratio:** 1:1

> Colored pencil art. Bright victorian Cluedo mansion — the Kitchen. Top view from the bottom, daytime, warm morning sunlight streaming through windows on the right wall, catching the copper pots. Warm copper and bright cream tones. A heavy butcher-block island, cast-iron pots hanging from a ceiling rack gleaming in the light, a coal-burning range with a kettle, flour dusted across the sun-warmed counter, a knife block, bundles of dried herbs, a pantry door slightly ajar letting in more light, an open toolbox on the floor with a wrench-shaped gap in the tray. Bright daylight on stone floor tiles.

---

### Grand Staircase — Day

**Ratio:** 4:5

> Colored pencil art. Bright victorian Cluedo mansion — the Grand Staircase. Top view from the bottom, brilliant daylight from skylights above and open doors below illuminating a wide, straight staircase in grand ballroom style. Warm mahogany and rich burgundy tones glowing in the sun. A long central flight with symmetrical carved banisters and a plush crimson runner rises directly to a sun-drenched landing. Crystal chandeliers sparkling brilliantly above while oil portraits of stern ancestors are clearly visible on the sunlit walls. A suit of armor gleaming at the landing. Polished brass handrails catching the daylight against warm wood paneling and a heavy newel post topped with a carved finial.

---

## Weapons

Weapon card illustrations. Each depicts the weapon as a central object on a dark surface, styled as evidence photography with a victorian twist.

---

### Candlestick

**Ratio:** 4:5

> Colored pencil art. Dark victorian noir Cluedo weapon — the Candlestick. A heavy brass candlestick on a mantle. Warm golden and tarnished bronze tones. Wax spatters on dark wood beneath. Dramatic side-lighting casting a long shadow.

---

### Knife

**Ratio:** 9:16

> Colored pencil art. Dark victorian noir Cluedo weapon — the Knife. A sharp carving knife with an ivory handle, laid diagonally on a white linen napkin. Cold steel blue and bone-white tones. The blade catches a glint of light along its edge. A single dark stain near the tip. Monogrammed handle. Background of polished dark marble.

---

### Lead Pipe

**Ratio:** 9:16

> Colored pencil art. Dark victorian noir Cluedo weapon — the Lead Pipe. A heavy dull-grey lead pipe, slightly bent, resting on wet cobblestones. Slate grey and rain-slicked charcoal tones. Beads of condensation along its surface. A gaslight reflection in a nearby puddle. Industrial grime and patina. Fog rolling in at the edges.

---

### Revolver

**Ratio:** 3:2

> Colored pencil art. Dark victorian noir Cluedo weapon — the Revolver. A snub-nosed six-shot revolver with a pearl grip, resting on a green felt card table. Gunmetal black and mother-of-pearl tones. The cylinder slightly open, one chamber empty. Scattered poker chips and a spent brass casing nearby. Warm lamplight from above.

---

### Rope

**Ratio:** 1:1

> Colored pencil art. Dark victorian noir Cluedo weapon — the Rope. A coil of thick hemp rope with a knotted loop, draped over a wooden banister post. Rough sisal tan and dark oak tones. Frayed fibers catching the light. The knot tied in a precise hangman's style. Shadows of staircase railings across the wall. Dusty, forgotten attic atmosphere.

---

### Wrench

**Ratio:** 4:5

> Colored pencil art. Dark victorian noir Cluedo weapon — the Wrench. A heavy iron pipe wrench with a rust-pitted jaw, resting on a workbench. Deep iron-oxide red and soot-black tones. Oil stains on the wooden bench surface. A torn work glove beside it. Background of brick wall with mounted gas pipes. Harsh overhead workshop light casting hard shadows.

---

## Characters — Flirtatious Variants

Alternate character portraits with a romantic, flirtatious tone. Think golden-hour lighting, lingering glances, and simmering tension.

---

### Miss Scarlett — Flirtatious

**Ratio:** 2:3

> Colored pencil art. Romantic victorian Cluedo portrait — Miss Scarlett. A stunning young woman leaning against a marble fireplace mantel, scarlet silk robe slipping off one shoulder, revealing a delicate lace chemise beneath. Half-lidded eyes and a teasing smile. Warm candlelight painting her skin in amber and rose tones. One finger tracing the rim of a champagne coupe. Tousled dark curls. Deep crimson and blush pink tones. Inviting, playful, magnetic.

---

### Colonel Mustard — Flirtatious

**Ratio:** 2:3

> Colored pencil art. Romantic victorian Cluedo portrait — Colonel Mustard. A ruggedly handsome older gentleman, mustard-gold dress shirt unbuttoned at the collar, sleeves rolled to the forearms revealing tanned, strong arms. Leaning back in a leather armchair with one leg crossed, a knowing smirk beneath his thick grey moustache. A rose tucked into his breast pocket. Brandy in hand, firelight dancing across his weathered features. Golden amber and warm honey tones. Confident, rakish, unexpectedly charming.

---

### Mrs. White — Flirtatious

**Ratio:** 2:3

> Colored pencil art. Romantic victorian Cluedo portrait — Mrs. White. A young woman with fiery red hair tumbling loose over bare shoulders, apron discarded on a kitchen chair behind her. Wearing a fitted cream blouse with the top buttons undone, leaning forward on a flour-dusted countertop with a coy grin. A smudge of flour on her cheek. Warm gaslight catching eyes full of mischief. A fresh-baked pie cooling nearby, steam curling upward. Warm ivory and cinnamon tones. Flirtatious, disarming, full of surprises.

---

### Reverend Green — Flirtatious

**Ratio:** 2:3

> Colored pencil art. Romantic victorian Cluedo portrait — Reverend Green. A devastatingly handsome young clergyman, dog collar removed and dangling from two fingers, dark green waistcoat fitted perfectly over a white shirt open at the throat. Leaning in a candlelit doorway with a slow, dangerous smile. Dark hair slightly disheveled as if he's been running his hands through it. One eyebrow raised in invitation. A glass of red wine in his other hand. Deep emerald and warm candlelight tones. Tempting, forbidden, irresistible.

---

### Mrs. Peacock — Flirtatious

**Ratio:** 2:3

> Colored pencil art. Romantic victorian Cluedo portrait — Mrs. Peacock. A regal woman reclining on a sapphire-blue velvet chaise longue, royal blue evening gown with a daring neckline, a peacock-feather fan held just below her chin, peering over it with smoldering dark eyes. Hair loosened from its chignon, a few dark curls cascading down her neck. A string of pearls wound loosely around one wrist. Moonlight through sheer curtains casting soft blue shadows. Sapphire and silver tones. Commanding, alluring, impossible to refuse.

---

### Professor Plum — Flirtatious

**Ratio:** 2:3

> Colored pencil art. Romantic victorian Cluedo portrait — Professor Plum. A tousle-haired academic perched on the edge of a cluttered desk, plum-purple waistcoat unbuttoned, shirtsleeves pushed up, glasses removed and dangling from his lips as he looks up with unexpected intensity. An open book forgotten in his lap. Ink stains on his fingers. Late-night lamplight warm on his face, casting the book-lined study in soft violet and gold. A half-written love poem visible on the desk behind him. Distracted, smoldering, surprisingly passionate.
