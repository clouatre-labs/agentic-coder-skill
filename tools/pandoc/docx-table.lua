function Table(el)
  el.attr.attributes["custom-style"] = "BorderedTable"
  for i, colspec in ipairs(el.colspecs) do
    el.colspecs[i] = {colspec[1], pandoc.ColWidthDefault}
  end
  return el
end
