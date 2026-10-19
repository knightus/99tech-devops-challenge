"""Minimal draw.io (diagrams.net) XML builder using the official AWS4 shape library.

Layouts are placed at explicit coordinates so diagrams stay tidy and
reproducible. The generated .drawio files can be opened and edited at
https://app.diagrams.net.
"""
from xml.sax.saxutils import escape

FONT = "fontFamily=Helvetica;"

# Icon fill colours by AWS category.
CATEGORY = {
    "compute": "#ED7100",
    "database": "#C925D1",
    "network": "#8C4FFF",
    "storage": "#7AA116",
    "integration": "#E7157B",
    "security": "#DD344C",
    "management": "#E7157B",
    "containers": "#ED7100",
    "general": "#232F3D",
}

GROUP = {
    "cloud": "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_aws_cloud;strokeColor=#232F3E;fillColor=none;fontColor=#232F3E;dashed=0;",
    "account": "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_account;strokeColor=#CD2264;fillColor=none;fontColor=#CD2264;dashed=0;",
    "region": "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_region;strokeColor=#00A4A6;fillColor=none;fontColor=#00A4A6;dashed=1;",
    "vpc": "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_vpc2;strokeColor=#8C4FFF;fillColor=#F9F6FF;fontColor=#8C4FFF;dashed=0;",
    "public": "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_public_subnet;strokeColor=#248814;fillColor=#F2F8F0;fontColor=#248814;dashed=0;",
    "private": "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_private_subnet;strokeColor=#147EBA;fillColor=#EEF5FA;fontColor=#147EBA;dashed=0;",
    "plain": "rounded=1;arcSize=4;strokeColor=#879196;fillColor=none;fontColor=#545B64;dashed=1;",
}

EDGE = {
    "request": "strokeColor=#545B64;",
    "data": "strokeColor=#0F766E;strokeWidth=2;",
    "optional": "strokeColor=#879196;dashed=1;",
    "new": "strokeColor=#B45309;strokeWidth=2;",
}


class Drawing:
    def __init__(self, title, subtitle=""):
        self.cells = []
        self.n = 0
        self.text("title", title, 40, 20, 1400, 40, size=26, bold=True)
        if subtitle:
            self.text("subtitle", subtitle, 40, 60, 1400, 24, size=14, color="#545B64")

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}-{self.n}"

    def text(self, cid, value, x, y, w, h, size=12, bold=False, color="#232F3E", align="left"):
        style = (
            f"text;html=1;strokeColor=none;fillColor=none;align={align};verticalAlign=middle;"
            f"whiteSpace=wrap;fontSize={size};fontStyle={1 if bold else 0};fontColor={color};{FONT}"
        )
        self._vertex(cid, value, style, x, y, w, h)
        return cid

    def group(self, value, kind, x, y, w, h, highlight=False):
        base = GROUP[kind]
        if highlight:
            base = base.replace("dashed=0;", "dashed=1;").replace("dashed=1;", "dashed=1;strokeWidth=2;")
        style = (
            "points=[];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=13;"
            "fontStyle=1;verticalAlign=top;align=left;spacingLeft=30;container=0;pointerEvents=0;"
            f"{base}{FONT}"
        )
        if kind == "plain":
            style = style.replace("spacingLeft=30;", "spacingLeft=10;spacingTop=4;")
        cid = self._id("group")
        self._vertex(cid, value, style, x, y, w, h)
        return cid

    def icon(self, value, res, category, x, y, size=56, mark=None, resource=False):
        """AWS icon with its label underneath. mark: None, 'added', 'changed'.

        resource=True draws a sub-resource shape (e.g. nat_gateway) instead of a service icon.
        """
        shape = f"shape=mxgraph.aws4.{res};strokeColor=none;" if resource else (
            f"shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{res};strokeColor=#ffffff;"
        )
        style = (
            "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
            f"fillColor={CATEGORY[category]};dashed=0;verticalLabelPosition=bottom;verticalAlign=top;"
            f"align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;{shape}{FONT}"
        )
        if mark:
            colour = {"added": "#15803D", "changed": "#B45309"}[mark]
            pad = 8
            self._vertex(
                self._id("mark"), "",
                f"rounded=1;arcSize=12;fillColor=none;strokeColor={colour};strokeWidth=3;dashed=0;{FONT}",
                x - pad, y - pad, size + 2 * pad, size + 2 * pad,
            )
        cid = self._id("icon")
        self._vertex(cid, value, style, x, y, size, size)
        return cid

    def generic(self, value, shape, x, y, size=56):
        """Non-AWS actor (users, external provider) using the AWS general icon set."""
        style = (
            "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;fillColor=#232F3D;"
            "strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;"
            f"html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.{shape};{FONT}"
        )
        cid = self._id("actor")
        self._vertex(cid, value, style, x, y, size, size)
        return cid

    def edge(self, src, dst, label="", kind="request", points=None, exit=None, entry=None):
        style = (
            "edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=1;rounded=0;"
            f"fontSize=11;labelBackgroundColor=#FFFFFF;{EDGE[kind]}{FONT}"
        )
        if exit:
            style += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
        if entry:
            style += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
        cid = self._id("edge")
        pts = ""
        if points:
            pts = "<Array as=\"points\">" + "".join(
                f'<mxPoint x="{px}" y="{py}" />' for px, py in points
            ) + "</Array>"
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" '
            f'edge="1" parent="1" source="{src}" target="{dst}">'
            f'<mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>'
        )
        return cid

    def legend(self, x, y, items):
        """items: list of (kind, text). Draws a small line-style legend."""
        self.group("Legend", "plain", x, y, 220, 30 + 24 * len(items))
        for i, (kind, text) in enumerate(items):
            yy = y + 34 + 24 * i
            a = self.text(self._id("lg"), "", x + 12, yy, 1, 1)
            b = self.text(self._id("lg"), "", x + 60, yy, 1, 1)
            self.edge(a, b, kind=kind)
            self.text(self._id("lgt"), text, x + 70, yy - 10, 145, 20, size=11, color="#545B64")

    def _vertex(self, cid, value, style, x, y, w, h):
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(value.replace(chr(10), "<br>"), {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" /></mxCell>'
        )

    def save(self, path):
        body = "".join(self.cells)
        xml = (
            '<mxfile host="app.diagrams.net"><diagram name="Page-1" id="page-1">'
            '<mxGraphModel grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
            'fold="1" page="0" pageScale="1" math="0" shadow="0"><root>'
            '<mxCell id="0" /><mxCell id="1" parent="0" />'
            f"{body}</root></mxGraphModel></diagram></mxfile>"
        )
        with open(path, "w", encoding="utf8", newline="\n") as f:
            f.write(xml)
