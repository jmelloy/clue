-- Parse card image prompts (from backend/app/games/holdem/cards.md) into
-- (deck_type, variant, rank, suit). The prompt column holds the full text
-- submitted to mage.space — i.e. the deck's section paragraph followed by
-- the per-card prompt — exactly as scripts/mage_generate.py builds it.
--
-- Vocabulary:
--   deck_type — Standard | Fun         (the "(Fun)" tag in the h1 heading)
--   variant   — Classic | Vintage | Modern | Web | Fantasy | Pinup
--   rank      — Ace | Jack | Queen | King
--   suit      — Hearts | Diamonds | Spades | Clubs
--
-- Rank/suit detection has two tiers:
--   1. Standard decks (Classic/Vintage/Modern) — every per-card prompt
--      includes the literal "<Rank> of <Suit>" phrase, so a couple of
--      LIKE patterns cover them all.
--   2. Fun decks (Web/Fantasy/Pinup) — per-card prompts describe a
--      character/scene rather than naming the card, so we fall back on
--      keyword matching: "young X" → Jack, "queen"/"woman"/"femme fatale"
--      → Queen, "king"/"gentleman"/"... man ..." → King, and the suit
--      shape/emblem ("heart-shaped", "trefoil", "spade crest", etc.).
--      A handful of Web face cards (e.g. Queen of Spades = "cybersecurity
--      queen ... shield with a lock icon") have no suit cue in the body
--      and fall through to NULL — the section glossary mentions all four
--      suits so it can't disambiguate. For those, fall back on file_name.
--
-- Written for SQLite (LIKE is case-insensitive over ASCII). For Postgres
-- swap LIKE for ILIKE, or use `~*` for true regex.

SELECT
    id,
    file_name,

    -- Deck type: Fun decks are tagged "(Fun)" in cards.md (Web / Fantasy /
    -- Pinup); the other three are Standard.
    CASE
        WHEN prompt LIKE '%software engineering and internet culture%'
          OR prompt LIKE '%Bright colorful digital illustration%'
          OR prompt LIKE '%High-fantasy illustration%'
          OR prompt LIKE '%Rich fantasy painting%'
          OR prompt LIKE '%1940s pin-up%'
          OR prompt LIKE '%Gil Elvgren%'
            THEN 'Fun'
        ELSE 'Standard'
    END AS deck_type,

    -- Variant: each section paragraph has a unique signature phrase.
    CASE
        WHEN prompt LIKE '%Traditional engraved playing card style%'
          OR prompt LIKE '%baroque scrollwork and filigree%'
            THEN 'Classic'
        WHEN prompt LIKE '%Sepia-toned watercolor%'
          OR prompt LIKE '%aged parchment%'
            THEN 'Vintage'
        WHEN prompt LIKE '%Flat geometric vector%'
          OR prompt LIKE '%Bauhaus%'
          OR prompt LIKE '%Swiss design%'
          OR prompt LIKE '%#E53935%'
          OR prompt LIKE '%#1A237E%'
            THEN 'Modern'
        WHEN prompt LIKE '%software engineering and internet culture%'
          OR prompt LIKE '%Bright colorful digital illustration%'
            THEN 'Web'
        WHEN prompt LIKE '%High-fantasy illustration%'
          OR prompt LIKE '%Rich fantasy painting%'
            THEN 'Fantasy'
        WHEN prompt LIKE '%1940s pin-up%'
          OR prompt LIKE '%Gil Elvgren%'
          OR prompt LIKE '%pin-up illustration%'
            THEN 'Pinup'
    END AS variant,

    -- Rank
    CASE
        -- Tier 1: Standard decks always say "<Rank> of <Suit>". The plural
        -- forms ("Aces", "Kings") that appear in section text won't match
        -- the trailing " of ".
        WHEN prompt LIKE '%Ace of %'   THEN 'Ace'
        WHEN prompt LIKE '%Jack of %'  THEN 'Jack'
        WHEN prompt LIKE '%Queen of %' THEN 'Queen'
        WHEN prompt LIKE '%King of %'  THEN 'King'

        -- Tier 2: Fun decks. Order matters — Jack must precede Queen/King
        -- because Pinup Jacks ("a young man in a sharp suit") would
        -- otherwise be caught by the King's " man " pattern.
        WHEN prompt LIKE '%young %'                   THEN 'Jack'
        WHEN prompt LIKE '% queen %'
          OR prompt LIKE '%femme fatale%'
          OR prompt LIKE '%glamorous woman%'
          OR prompt LIKE '%elegant woman%'
          OR prompt LIKE '%vivacious woman%'
          OR prompt LIKE '%product manager%'          THEN 'Queen'
        WHEN prompt LIKE '% king %'
          OR prompt LIKE '%gentleman%'
          OR prompt LIKE '%suave man%'
          OR prompt LIKE '%rugged man%'
          OR prompt LIKE '%jovial man%'
          OR prompt LIKE '%tech CEO%'                 THEN 'King'

        -- Aces in Fun decks have no character — only a giant suit shape.
        WHEN prompt LIKE '%a large stylized %'
          OR prompt LIKE '%a large diamond shape%'
          OR prompt LIKE '%a large spade shape%'
          OR prompt LIKE '%a large trefoil club shape%'
          OR prompt LIKE '%a blazing heart%'
          OR prompt LIKE '%enormous diamond crystal%'
          OR prompt LIKE '%a dark spade formed%'
          OR prompt LIKE '%ancient trefoil club%'
          OR prompt LIKE '%heart shape formed%'
          OR prompt LIKE '%diamond shape made%'
          OR prompt LIKE '%spade shape formed%'
          OR prompt LIKE '%trefoil club shape formed%' THEN 'Ace'
    END AS rank,

    -- Suit
    CASE
        -- Tier 1: Standard decks
        WHEN prompt LIKE '% of Hearts%'   THEN 'Hearts'
        WHEN prompt LIKE '% of Diamonds%' THEN 'Diamonds'
        WHEN prompt LIKE '% of Spades%'   THEN 'Spades'
        WHEN prompt LIKE '% of Clubs%'    THEN 'Clubs'

        -- Tier 2: Fun decks. Match singular lowercase shape/emblem
        -- mentions from the per-card prompt — these are absent from the
        -- section glossary (which uses capitalized plurals like "Hearts =
        -- Like/Love"). Spades is checked before Hearts so Pinup Q/S
        -- ("spade-shaped masquerade mask") isn't shadowed by anything.
        WHEN prompt LIKE '%spade shape%'
          OR prompt LIKE '%spade-shape%'
          OR prompt LIKE '%spade emblem%'
          OR prompt LIKE '%spade crest%'
          OR prompt LIKE '%spade badge%'
          OR prompt LIKE '%dark spade%'
          OR prompt LIKE '%spade-shaped%'
          -- Web: Spades = Terminal cursors (per the section glossary).
          -- These tech-archetype keywords only appear in the Web spades
          -- per-card prompts, never in the section text.
          OR prompt LIKE '%hacker%'
          OR prompt LIKE '%cybersecurity%'
          OR prompt LIKE '%sysadmin%'                  THEN 'Spades'
        WHEN prompt LIKE '%trefoil%'
          OR prompt LIKE '%club shape%'
          OR prompt LIKE '%club-shaped%'
          OR prompt LIKE '%club trefoil%'
          -- Web: Clubs = Wi-Fi signals; these tech-archetype keywords are
          -- only in Web clubs per-card prompts. Fantasy: K/C is "treant
          -- king" + Q/C is "archdruid queen with antlers" — neither says
          -- "club", but those words are unique to those cards.
          OR prompt LIKE '%DevOps%'
          OR prompt LIKE '%network engineer%'
          OR prompt LIKE '%open-source%'
          OR prompt LIKE '%pull request%'
          OR prompt LIKE '%fiber optic%'
          OR prompt LIKE '%treant%'
          OR prompt LIKE '%archdruid%'
          OR prompt LIKE '%antlers%'                   THEN 'Clubs'
        WHEN prompt LIKE '%diamond shape%'
          OR prompt LIKE '%diamond-shape%'
          OR prompt LIKE '%diamond crystal%'
          OR prompt LIKE '%diamond-pattern%'
          OR prompt LIKE '%diamond-stud%'
          OR prompt LIKE '%diamond hands%'
          OR prompt LIKE '%diamond facet%'
          OR prompt LIKE '%diamond chip%'
          OR prompt LIKE '%diamond crown%'
          OR prompt LIKE '%diamond icon%'
          -- Fantasy: J/D + Q/D have bare "diamond" — these adjective
          -- forms aren't in the section glossary ("Diamonds = Earth").
          OR prompt LIKE '%glowing diamond%'
          OR prompt LIKE '%prismatic diamond%'         THEN 'Diamonds'
        WHEN prompt LIKE '%heart shape%'
          OR prompt LIKE '%heart-shape%'
          OR prompt LIKE '%heart-shaped%'
          OR prompt LIKE '%heart emblem%'
          OR prompt LIKE '%heart amulet%'
          OR prompt LIKE '%heart notification%'
          OR prompt LIKE '%heart icon%'
          OR prompt LIKE '%heart motif%'
          OR prompt LIKE '%blazing heart%'
          OR prompt LIKE '%Valentine%'
          OR prompt LIKE '%lipstick%'                  THEN 'Hearts'
    END AS suit

FROM images
WHERE prompt IS NOT NULL;
