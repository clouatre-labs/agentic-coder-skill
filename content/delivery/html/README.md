# HTML Documentation Portals

## Overview

This directory contains static HTML portals generated from markdown delivery documents in
`content/delivery/`. Each portal is a self-contained, multi-page site and requires no build
step or external dependencies.

## Generating a Portal

1. Write (or confirm) your markdown delivery document in `content/delivery/`.
2. Open [goose](https://github.com/aaif-goose/goose) or any AI assistant and run the prompt below,
   substituting the placeholders.
3. The assistant outputs all files to `content/delivery/html/<portal-name>/`.
4. Commit the generated folder alongside the source markdown.

## Generation Prompt

```
Create an HTML documentation portal based on `<SOURCE_MARKDOWN_PATH>`.
Create a Bootstrap-style site with left-hand navigation.
The landing page should be `index.html`; create as many other pages as needed.
Break out the sections of the markdown source into multiple pages.
Output all files to `content/delivery/html/<PORTAL_NAME>/`.
```

Replace `<SOURCE_MARKDOWN_PATH>` with the path to your markdown file (e.g.
`content/delivery/2024-02-25-aws-replatform-example.md`) and `<PORTAL_NAME>` with a
short slug (e.g. `example-report`).

## HTML-Only Customisations

Some content exists only in the generated HTML and is not derived from the source markdown.
**These elements must be re-applied manually after any regeneration:**

- **Metrics / hero tiles** (e.g. executive summary cards on `index.html`): numbers are
  not in the markdown; the source of truth is the delivery markdown and `AGENTS.md`.
  Update the HTML tiles whenever those sources change.
- **Figures not embedded in the markdown** (e.g. `architecture.html` Figure 1 renders
  `images/01-request-flow.png` with a caption below): ensure the image and caption
  survive regeneration.

## Offline Viewing

1. Download or zip the portal folder.
2. Open `index.html` in any browser.

All links are relative. No external dependencies or internet connection required.

## Styling

Define a project brand guide in `tools/html/` if needed. Layout features a fixed sidebar,
prev/next page controls, and responsive tables and code blocks.
