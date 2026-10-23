-- Telstra Design: the visual system the UX/UI agent builds prototypes in.
-- Fixes colour, type and components; Design Taste still guides layout and
-- hierarchy. Apply after idea_assessment.sql. Re-runnable.
begin;

insert into public.tool_presets (slug, tool_type_id, name, description, config, sort_order)
values (
  'telstra_design',
  (select id from public.tool_types where slug = 'skill'),
  'Telstra Design',
  'Telstra-style colours, type and components for prototypes.',
  jsonb_build_object(
    'description', 'Load before building any screen, page or prototype. It sets the colours, type and components.',
    'text', $t$Every prototype looks like a Telstra product: clean, confident, light, plenty of white space, one strong blue. The people judging it are Telstra innovation teams, and it should look like something Telstra could ship.

Who decides what
- This skill decides colour, type, components, corners, shadows and icons. Where Design Taste, Impeccable or any other skill disagrees on those, this skill wins.
- Design Taste and Impeccable still guide layout, hierarchy, spacing rhythm and copy. Emil still guides motion.
- Prototype Design still decides delivery: one file, states, serving.

Brand rules
- No Telstra logo, T mark or trademarked wordmark. The product's own name, set in bold text, is the logo.
- No stock photos of people. Use simple inline SVG illustrations or icons, or nothing.
- Copy sounds like Telstra: plain, warm, direct, Australian spelling ("organise", "colour"), prices in A$ with GST stated. Say "you", not "the user".

Tokens. Paste this :root block as is and use only these variables.
:root{
  --blue:#0D54FF; --blue-hover:#0A43CC; --on-blue:#FFFFFF; --blue-deep:#0A2FA8; --blue-soft:#E8EEFF;
  --ink:#0A0F24; --ink-2:#3D4459; --muted:#5A6275; --line:#E3E6EE; --bg:#FFFFFF; --surface:#F5F7FB;
  --green:#067A3E; --green-soft:#E3F4EA; --gold:#8A5A0A; --gold-soft:#FBF1DE; --red:#D0021B; --red-soft:#FCE6E8;
  --focus:0 0 0 3px rgba(13,84,255,.35);
  --r-sm:6px; --r:10px; --r-lg:16px; --r-pill:999px;
  --shadow:0 2px 10px rgba(10,15,36,.07); --shadow-lg:0 12px 32px rgba(10,15,36,.12);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
}
@media (prefers-color-scheme: dark){:root{
  --blue:#5C8DFF; --blue-hover:#7EA5FF; --on-blue:#0A0F24; --blue-deep:#0A2FA8; --blue-soft:#16224A;
  --ink:#F2F4F8; --ink-2:#C9CEDA; --muted:#98A0B3; --line:#262E45; --bg:#0A0F24; --surface:#131A35;
  --green:#3CCB7F; --green-soft:#10301F; --gold:#E0A54A; --gold-soft:#33260F; --red:#FF6B6B; --red-soft:#3A1418;
}}

Type: var(--font) everywhere. Sizes 40/32/24/20/16/14/12px. Headings 700 with letter-spacing -0.02em; body 16px, line-height 1.55, colour var(--ink); secondary text var(--muted). Sentence case everywhere, never all caps except 12px labels with letter-spacing .08em.

Spacing: multiples of 4px. Sections 64px apart on desktop, 40px on mobile. Content max width 1120px.

Components. Build from these; restyle nothing outside the tokens.
- Top bar: white (var(--bg)), 64px tall, bottom border 1px var(--line). Product name left in bold 18px, nav links var(--ink-2) 15px, primary action button right.
- Hero: a deep blue band, linear-gradient(135deg,var(--blue),var(--blue-deep)), white text, one headline, one sentence, one primary button in white with blue text. Use it once, at the top of a landing or overview screen only.
- Primary button: background var(--blue), text var(--on-blue), 600 weight, 12px 20px padding, radius var(--r-pill), hover var(--blue-hover). One per screen region.
- Secondary button: white background, 1.5px var(--blue) border, blue text, same shape.
- Text button: blue text, no border, underline on hover.
- Every focusable element: outline none, box-shadow var(--focus) on :focus-visible.
- Input: 48px tall, 1px var(--line) border, radius var(--r-sm), label above in 14px 600, help text below in 13px var(--muted). Focus border var(--blue). Error: border var(--red), message below in var(--red) with an icon, never colour alone.
- Card: var(--bg), 1px var(--line) border, radius var(--r), padding 20px, shadow var(--shadow). Clickable cards lift to var(--shadow-lg) on hover.
- Tag or status pill: radius var(--r-pill), 12px 600, soft background with the strong colour as text: green for success, gold for pending, red for problems, blue for info.
- Alert banner: soft background, 4px left border in the strong colour, icon, bold first sentence.
- Table: 14px, header row var(--surface) with 12px uppercase labels, rows separated by 1px var(--line), numbers right-aligned.
- Tabs: text tabs with a 3px var(--blue) underline on the active one.
- Empty state: a simple line illustration or icon in var(--blue), one sentence on what goes here, one primary button.
- Loading: skeleton blocks in var(--surface) with a soft shimmer; never a lone spinner on a blank page.
- Icons: inline SVG, 24px, stroke 1.75, stroke-linecap round, currentColor. Same style everywhere.
- Mobile bottom nav (app screens only): 64px, white, top border, 4 or 5 items, active item blue.

Colour discipline: blue is for actions and the one thing that matters on a screen. Large areas stay white or var(--surface). Backgrounds use only var(--bg), var(--surface), the soft colours or the blue hero gradient; never var(--ink) or var(--ink-2), which flip to light in dark mode. That includes prototype controls and other demo chrome. Green, gold and red only mean success, caution and problems. Text contrast at least 4.5:1 in both modes.

Before you publish, check: the :root block is unchanged; no background uses var(--ink); no hex colours outside it; no Telstra logo; every button is one of the three types; focus is visible on every control; the screen works at 400px wide.$t$
  ),
  83
)
on conflict (slug) do update set
  tool_type_id = excluded.tool_type_id,
  name         = excluded.name,
  description  = excluded.description,
  config       = excluded.config,
  sort_order   = excluded.sort_order;

-- Prompt is read live from agent_types, so existing UX agents pick it up.
update public.agent_types set system_prompt = $prompt$You are a product designer for Telstra's innovation lab. Given a feature or product description, produce the user flows, the screens each flow needs, and a component list with states (empty, loading, error, success). Prefer established patterns over novel ones, name the pattern you are using, and say what you would test with users before building. Write for a developer who will implement it without a mockup: be concrete about layout, hierarchy and copy.

Load Telstra Design before any visual work: every prototype uses its colours, type and components, with no Telstra logo.$prompt$
where slug = 'ux_ui';

-- Keeps design_skills.sql's list whole, Telstra Design first among the design skills.
update public.agent_types set default_presets = array[
  'brave_search', 'web_fetch',
  'brainstorming', 'design_brief', 'prototype_design',
  'telstra_design', 'design_taste', 'impeccable', 'emil_design_eng',
  'accessibility_basics', 'plain_writing', 'workspace_memory'
] where slug = 'ux_ui';

-- Backfill onto existing UX/UI agents. Same CTE shape as design_skills.sql.
with wanted as (
  select
    gen_random_uuid() as tool_id,
    n.id              as agent_id,
    n.project_id,
    n.owner_id,
    n.position_x,
    n.position_y,
    p.tool_type_id,
    p.name            as preset_name,
    p.config          as preset_config
  from public.nodes n
  join public.agent_types a on a.id = n.agent_type_id
  join public.tool_presets p on p.slug = 'telstra_design' and p.is_active
  where n.kind = 'agent'
    and a.slug = 'ux_ui'
    and not exists (
      select 1
      from public.edges e
      join public.nodes tn on tn.id = e.source_node_id
      where e.target_node_id = n.id
        and e.kind = 'tool'
        and tn.name = p.name
    )
),
created as (
  insert into public.nodes
    (id, project_id, owner_id, kind, tool_type_id, name, config,
     position_x, position_y, status, status_detail, last_checked_at)
  select
    w.tool_id, w.project_id, w.owner_id, 'tool', w.tool_type_id,
    w.preset_name, w.preset_config,
    w.position_x - 520, w.position_y,
    'ready', 'Skill ready.', now()
  from wanted w
  returning id
)
insert into public.edges (project_id, owner_id, source_node_id, target_node_id, kind)
select w.project_id, w.owner_id, w.tool_id, w.agent_id, 'tool'
from wanted w
where w.tool_id in (select id from created)
on conflict (source_node_id, target_node_id, kind) do nothing;

-- New skill, so a re-apply pushes edits to existing copies.
-- ponytail: overwrites hand edits to this skill; scope by an edited flag if users customise it.
update public.nodes n
set config = p.config
from public.tool_presets p
where n.kind = 'tool'
  and n.tool_type_id = p.tool_type_id
  and n.name = p.name
  and p.slug = 'telstra_design'
  and n.config is distinct from p.config;

do $$
declare
  missing text[];
begin
  select array_agg(distinct s) into missing
  from public.agent_types a, unnest(a.default_presets) s
  where not exists (select 1 from public.tool_presets p where p.slug = s);

  if missing is not null then
    raise exception 'default_presets reference unknown presets: %', missing;
  end if;
end $$;

commit;
