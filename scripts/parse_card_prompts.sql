-- Parse card image prompts (from backend/app/games/holdem/cards.md) into
-- (deck_type, variant, rank, suit). The prompt column holds the full text
-- submitted to mage.space — exactly as scripts/mage_generate.py builds it.
--
-- Targets Postgres (uses ILIKE for case-insensitive matching). Verified
-- against the full production dump: all 1089 prompts classify into a
-- non-NULL (variant, rank, suit).
--
-- Vocabulary:
--   deck_type — Standard | Fun         (the "(Fun)" tag in the h1 heading)
--   variant   — Classic | Vintage | Modern | Web | Fantasy | Pinup
--   rank      — Ace | Jack | Queen | King
--   suit      — Hearts | Diamonds | Spades | Clubs
--
-- Variant detection: each section preamble has a unique signature phrase
-- (Sepia/parchment, Flat geometric/Bauhaus/hex colors, etc.). Classic is
-- the catch-all and runs LAST — it covers two cases:
--   (a) prompts containing the section preamble ("Traditional engraved
--       playing card style", "baroque scrollwork and filigree"); and
--   (b) ~258 production prompts that drop the preamble and start
--       directly with "Black/Red [ink only,] line art on a white
--       background. Playing card design — <Rank> of <Suit>." Those
--       still describe the engraved monochrome aesthetic but have no
--       preamble keyword, so we match the per-card opener.
--
-- Rank/suit detection has two tiers:
--   1. Standard decks (Classic/Vintage/Modern) — every per-card prompt
--      includes the literal "<Rank> of <Suit>" phrase, so a couple of
--      ILIKE patterns cover them all.
--   2. Fun decks (Web/Fantasy/Pinup) — per-card prompts describe a
--      character/scene rather than naming the card, so we fall back on
--      keyword matching: "young X" → Jack, "queen"/"woman"/"femme fatale"
--      → Queen, "king"/"gentleman"/"... man ..." → King, and the suit
--      shape/emblem ("heart-shaped", "trefoil", "spade crest", etc.).

SELECT
    id,
    file_name,

    -- Deck type: Fun decks are tagged "(Fun)" in cards.md (Web / Fantasy /
    -- Pinup); the other three are Standard.
    CASE
        WHEN prompt ILIKE '%software engineering and internet culture%'
          OR prompt ILIKE '%Bright colorful digital illustration%'
          OR prompt ILIKE '%High-fantasy illustration%'
          OR prompt ILIKE '%Rich fantasy painting%'
          OR prompt ILIKE '%1940s pin-up%'
          OR prompt ILIKE '%Gil Elvgren%'
            THEN 'Fun'
        ELSE 'Standard'
    END AS deck_type,

    -- Variant: each section paragraph has a unique signature phrase.
    -- Classic runs LAST as the catch-all — see header note for why.
    CASE
        WHEN prompt ILIKE '%Sepia-toned watercolor%'
          OR prompt ILIKE '%aged parchment%'
            THEN 'Vintage'
        WHEN prompt ILIKE '%Flat geometric vector%'
          OR prompt ILIKE '%Bauhaus%'
          OR prompt ILIKE '%Swiss design%'
          OR prompt ILIKE '%#E53935%'
          OR prompt ILIKE '%#1A237E%'
            THEN 'Modern'
        WHEN prompt ILIKE '%software engineering and internet culture%'
          OR prompt ILIKE '%Bright colorful digital illustration%'
            THEN 'Web'
        WHEN prompt ILIKE '%High-fantasy illustration%'
          OR prompt ILIKE '%Rich fantasy painting%'
            THEN 'Fantasy'
        WHEN prompt ILIKE '%1940s pin-up%'
          OR prompt ILIKE '%Gil Elvgren%'
          OR prompt ILIKE '%pin-up illustration%'
            THEN 'Pinup'
        WHEN prompt ILIKE '%Traditional engraved playing card style%'
          OR prompt ILIKE '%baroque scrollwork and filigree%'
          OR prompt ILIKE '%line art on a white background. Playing card design%'
          OR prompt ILIKE '%line art on a white background. Playing card center artwork%'
            THEN 'Classic'
    END AS variant,

    -- Rank
    CASE
        -- Tier 1: Standard decks always say "<Rank> of <Suit>". The plural
        -- forms ("Aces", "Kings") that appear in section text won't match
        -- the trailing " of ".
        WHEN prompt ILIKE '%Ace of %'   THEN 'Ace'
        WHEN prompt ILIKE '%Jack of %'  THEN 'Jack'
        WHEN prompt ILIKE '%Queen of %' THEN 'Queen'
        WHEN prompt ILIKE '%King of %'  THEN 'King'

        -- Tier 2: Fun decks. Order matters — Jack must precede Queen/King
        -- because Pinup Jacks ("a young man in a sharp suit") would
        -- otherwise be caught by the King's " man " pattern.
        WHEN prompt ILIKE '%young %'                   THEN 'Jack'
        WHEN prompt ILIKE '% queen %'
          OR prompt ILIKE '%femme fatale%'
          OR prompt ILIKE '%glamorous woman%'
          OR prompt ILIKE '%elegant woman%'
          OR prompt ILIKE '%vivacious woman%'
          OR prompt ILIKE '%product manager%'          THEN 'Queen'
        WHEN prompt ILIKE '% king %'
          OR prompt ILIKE '%gentleman%'
          OR prompt ILIKE '%suave man%'
          OR prompt ILIKE '%rugged man%'
          OR prompt ILIKE '%jovial man%'
          OR prompt ILIKE '%tech CEO%'                 THEN 'King'

        -- Aces in Fun decks have no character — only a giant suit shape.
        WHEN prompt ILIKE '%a large stylized %'
          OR prompt ILIKE '%a large diamond shape%'
          OR prompt ILIKE '%a large spade shape%'
          OR prompt ILIKE '%a large trefoil club shape%'
          OR prompt ILIKE '%a blazing heart%'
          OR prompt ILIKE '%enormous diamond crystal%'
          OR prompt ILIKE '%a dark spade formed%'
          OR prompt ILIKE '%ancient trefoil club%'
          OR prompt ILIKE '%heart shape formed%'
          OR prompt ILIKE '%diamond shape made%'
          OR prompt ILIKE '%spade shape formed%'
          OR prompt ILIKE '%trefoil club shape formed%' THEN 'Ace'
    END AS rank,

    -- Suit
    CASE
        -- Tier 1: Standard decks
        WHEN prompt ILIKE '% of Hearts%'   THEN 'Hearts'
        WHEN prompt ILIKE '% of Diamonds%' THEN 'Diamonds'
        WHEN prompt ILIKE '% of Spades%'   THEN 'Spades'
        WHEN prompt ILIKE '% of Clubs%'    THEN 'Clubs'

        -- Tier 2: Fun decks. Match singular lowercase shape/emblem
        -- mentions from the per-card prompt — these are absent from the
        -- section glossary (which uses capitalized plurals like "Hearts =
        -- Like/Love"). Spades is checked before Hearts so Pinup Q/S
        -- ("spade-shaped masquerade mask") isn't shadowed by anything.
        WHEN prompt ILIKE '%spade shape%'
          OR prompt ILIKE '%spade-shape%'
          OR prompt ILIKE '%spade emblem%'
          OR prompt ILIKE '%spade crest%'
          OR prompt ILIKE '%spade badge%'
          OR prompt ILIKE '%dark spade%'
          OR prompt ILIKE '%spade-shaped%'
          -- Web: Spades = Terminal cursors (per the section glossary).
          -- These tech-archetype keywords only appear in the Web spades
          -- per-card prompts, never in the section text.
          OR prompt ILIKE '%hacker%'
          OR prompt ILIKE '%cybersecurity%'
          OR prompt ILIKE '%sysadmin%'                  THEN 'Spades'
        WHEN prompt ILIKE '%trefoil%'
          OR prompt ILIKE '%club shape%'
          OR prompt ILIKE '%club-shaped%'
          OR prompt ILIKE '%club trefoil%'
          -- Web: Clubs = Wi-Fi signals; these tech-archetype keywords are
          -- only in Web clubs per-card prompts. Fantasy: K/C is "treant
          -- king" + Q/C is "archdruid queen with antlers" — neither says
          -- "club", but those words are unique to those cards.
          OR prompt ILIKE '%DevOps%'
          OR prompt ILIKE '%network engineer%'
          OR prompt ILIKE '%open-source%'
          OR prompt ILIKE '%pull request%'
          OR prompt ILIKE '%fiber optic%'
          OR prompt ILIKE '%treant%'
          OR prompt ILIKE '%archdruid%'
          OR prompt ILIKE '%antlers%'                   THEN 'Clubs'
        WHEN prompt ILIKE '%diamond shape%'
          OR prompt ILIKE '%diamond-shape%'
          OR prompt ILIKE '%diamond crystal%'
          OR prompt ILIKE '%diamond-pattern%'
          OR prompt ILIKE '%diamond-stud%'
          OR prompt ILIKE '%diamond hands%'
          OR prompt ILIKE '%diamond facet%'
          OR prompt ILIKE '%diamond chip%'
          OR prompt ILIKE '%diamond crown%'
          OR prompt ILIKE '%diamond icon%'
          -- Fantasy: J/D + Q/D have bare "diamond" — these adjective
          -- forms aren't in the section glossary ("Diamonds = Earth").
          OR prompt ILIKE '%glowing diamond%'
          OR prompt ILIKE '%prismatic diamond%'         THEN 'Diamonds'
        WHEN prompt ILIKE '%heart shape%'
          OR prompt ILIKE '%heart-shape%'
          OR prompt ILIKE '%heart-shaped%'
          OR prompt ILIKE '%heart emblem%'
          OR prompt ILIKE '%heart amulet%'
          OR prompt ILIKE '%heart notification%'
          OR prompt ILIKE '%heart icon%'
          OR prompt ILIKE '%heart motif%'
          OR prompt ILIKE '%blazing heart%'
          OR prompt ILIKE '%Valentine%'
          OR prompt ILIKE '%lipstick%'                  THEN 'Hearts'
    END AS suit

FROM images
WHERE prompt IS NOT NULL;
