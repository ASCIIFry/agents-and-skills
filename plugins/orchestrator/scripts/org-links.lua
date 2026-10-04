-- Pandoc filter for org → GitHub Markdown.
-- Turns org in-file heading links ([[Heading]]), which pandoc emits as
-- "spurious-link" spans, into links to GitHub's heading anchors, and
-- renders #+TITLE as a level-1 heading.

local function github_slug(text)
  -- UTF-8 aware lowercasing; keep non-ASCII letters (e.g. umlauts) like GitHub.
  local s = pandoc.text.lower(text)
  s = s:gsub("[^%w%s%-_\128-\255]", "")
  s = s:gsub("%s", "-")
  return s
end

function Span(el)
  local target = el.attributes["target"]
  if el.classes:includes("spurious-link") and target then
    return pandoc.Link(pandoc.Str(target), "#" .. github_slug(target))
  end
end

function Pandoc(doc)
  local title = doc.meta.title
  if title then
    table.insert(doc.blocks, 1, pandoc.Header(1, pandoc.utils.stringify(title)))
  end
  return doc
end
