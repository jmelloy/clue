-- Stage tags for card images into a session-scoped temp table.
--
-- Re-uses the variant/rank/suit detection logic from
-- scripts/parse_card_prompts.sql, then emits five tag rows per image:
--
--   project:card-deck                                      -- collection
--   project:card-deck:<variant>:<rank> of <suit>           -- fully-qualified
--   <suit>                                                 -- bare suit
--   <rank>                                                 -- bare rank
--   project:cards-<variant>:card:<rank> of <suit>          -- per-deck card id
--
-- The card identifier follows the cards.md heading convention
-- ("### Ace of Hearts") — i.e. "<rank> of <suit>".
--
-- Run: psql -d <db> -f scripts/insert_card_tags.sql
--
-- The temp table persists for the rest of the psql session, so you can
-- review the rows before bulk-inserting into your real tags table:
--
--   SELECT tag, COUNT(*) FROM tmp_image_tags GROUP BY tag ORDER BY tag;
--   INSERT INTO image_tags(image_id, tag) SELECT image_id, tag FROM tmp_image_tags;

\set ON_ERROR_STOP on

CREATE TEMP TABLE IF NOT EXISTS tmp_image_tags (
    image_id BIGINT NOT NULL,
    tag      TEXT   NOT NULL,
    PRIMARY KEY (image_id, tag)
);

WITH parsed AS (
    SELECT
        id AS image_id,

        -- Variant: which themed deck the prompt came from.
        CASE
            WHEN prompt ILIKE '%Traditional engraved playing card style%'
              OR prompt ILIKE '%baroque scrollwork and filigree%'
                THEN 'Classic'
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
        END AS variant,

        -- Rank: tier 1 = Standard decks ("<Rank> of <Suit>" appears verbatim);
        -- tier 2 = Fun decks (keyword fallbacks).
        CASE
            WHEN prompt ILIKE '%Ace of %'   THEN 'Ace'
            WHEN prompt ILIKE '%Jack of %'  THEN 'Jack'
            WHEN prompt ILIKE '%Queen of %' THEN 'Queen'
            WHEN prompt ILIKE '%King of %'  THEN 'King'
            WHEN prompt ILIKE '%young %'                    THEN 'Jack'
            WHEN prompt ILIKE '% queen %'
              OR prompt ILIKE '%femme fatale%'
              OR prompt ILIKE '%glamorous woman%'
              OR prompt ILIKE '%elegant woman%'
              OR prompt ILIKE '%vivacious woman%'
              OR prompt ILIKE '%product manager%'           THEN 'Queen'
            WHEN prompt ILIKE '% king %'
              OR prompt ILIKE '%gentleman%'
              OR prompt ILIKE '%suave man%'
              OR prompt ILIKE '%rugged man%'
              OR prompt ILIKE '%jovial man%'
              OR prompt ILIKE '%tech CEO%'                  THEN 'King'
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

        -- Suit: tier 1 + tier 2 as in parse_card_prompts.sql.
        CASE
            WHEN prompt ILIKE '% of Hearts%'   THEN 'Hearts'
            WHEN prompt ILIKE '% of Diamonds%' THEN 'Diamonds'
            WHEN prompt ILIKE '% of Spades%'   THEN 'Spades'
            WHEN prompt ILIKE '% of Clubs%'    THEN 'Clubs'
            WHEN prompt ILIKE '%spade shape%'
              OR prompt ILIKE '%spade-shape%'
              OR prompt ILIKE '%spade emblem%'
              OR prompt ILIKE '%spade crest%'
              OR prompt ILIKE '%spade badge%'
              OR prompt ILIKE '%dark spade%'
              OR prompt ILIKE '%spade-shaped%'
              OR prompt ILIKE '%hacker%'
              OR prompt ILIKE '%cybersecurity%'
              OR prompt ILIKE '%sysadmin%'                  THEN 'Spades'
            WHEN prompt ILIKE '%trefoil%'
              OR prompt ILIKE '%club shape%'
              OR prompt ILIKE '%club-shaped%'
              OR prompt ILIKE '%club trefoil%'
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
    WHERE prompt IS NOT NULL
)
INSERT INTO tmp_image_tags (image_id, tag)
-- 1. Collection-level tag — every image identified as belonging to a deck.
SELECT image_id, 'project:card-deck'
FROM   parsed
WHERE  variant IS NOT NULL

UNION ALL
-- 2. Fully-qualified tag with deck variant + card identifier.
SELECT image_id,
       format('project:card-deck:%s:%s of %s', variant, rank, suit)
FROM   parsed
WHERE  variant IS NOT NULL AND rank IS NOT NULL AND suit IS NOT NULL

UNION ALL
-- 3. Bare suit tag.
SELECT image_id, suit
FROM   parsed
WHERE  suit IS NOT NULL

UNION ALL
-- 4. Bare rank tag.
SELECT image_id, rank
FROM   parsed
WHERE  rank IS NOT NULL

UNION ALL
-- 5. Per-deck card identifier.
SELECT image_id,
       format('project:cards-%s:card:%s of %s', variant, rank, suit)
FROM   parsed
WHERE  variant IS NOT NULL AND rank IS NOT NULL AND suit IS NOT NULL

ON CONFLICT (image_id, tag) DO NOTHING;

\echo
\echo 'Staged tags by tag value:'
SELECT tag, COUNT(*) AS image_count
FROM   tmp_image_tags
GROUP  BY tag
ORDER  BY tag;

\echo
\echo 'Staged tag rows total:'
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT image_id) AS distinct_images
FROM   tmp_image_tags;
