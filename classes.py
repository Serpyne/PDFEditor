from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *

from pymupdf import Rect, Annot
import pypdf
from pypdf.generic import AnnotationBuilder
from datetime import datetime
from uuid import uuid4

def rgb_to_hex(rgb: list | tuple):
    return '#%02x%02x%02x' % tuple(rgb)

class Ink:
    def __init__(self, id: str, points: list, color: tuple, width: int, opacity: float):
        self.id = id
        self.points = points
        self.color = [int(x * 255) for x in color]
        self.width = width
        self.opacity = opacity
        self.highlight = (width == 0)

class Square:
    def __init__(self, id: str, rect: Rect, opacity: float,
                 border_color: tuple, fill_color: tuple, border_width: int):
        self.id = id
        self.pos = [rect.x0, rect.y0]
        self.size = [rect.width, rect.height]
        self.opacity = opacity
        self.border_color = [int(x * 255) for x in border_color]
        self.fill_color = [int(x * 255) for x in fill_color]
        self.border_width = border_width

    def colliderect(self, rect: QRect | QRectF) -> bool:
        left = self.pos[0]
        top = self.pos[1]
        right = left + self.size[0]
        bottom = top + self.size[1]

        if left > rect.right():
            return False
        if right < rect.left():
            return False
        if top > rect.bottom():
            return False
        if bottom < rect.top():
            return False
        
        return True
    
    def draw(self, painter: QPainter, zoom: float):
        pos = QPointF(*self.pos) * zoom
        size = QSizeF(*self.size) * zoom

        border_color = QColor(*self.border_color)
        fill_color = QColor(*self.fill_color, int(self.opacity * 255))
        painter.setPen(QPen(border_color, self.border_width * zoom, Qt.PenStyle.SolidLine))
        painter.setBrush(QBrush(fill_color))
        painter.drawRect(QRectF(pos, size))

    def export(self):
        ...
        # rect = {"/Type": "/Annot", "/Subtype": "/Square"}
        # rect["/Rect"] = [self.pos[0], self.pos[1], self.pos[0] + self.size[0], self.pos[1] + self.size[1]]
        # rect["/C"] = [c / 255 for c in self.border_color]
        # rect["/IC"] = [c / 255 for c in self.fill_color]
        # return rect
    
# FONT_STYLES = {"italic": QFont.Style.StyleItalic, "normal": QFont.Style.StyleNormal, "oblique": QFont.Style.StyleOblique}
# FONT_WEIGHTS = {
#     "thin": QFont.Weight.Thin,
#     "extralight": QFont.Weight.ExtraLight,
#     "light": QFont.Weight.Light,
#     "normal": QFont.Weight.Normal,
#     "medium": QFont.Weight.Medium,
#     "demibold": QFont.Weight.DemiBold,
#     "bold": QFont.Weight.Bold,
#     "extrabold": QFont.Weight.ExtraBold,
#     "black": QFont.Weight.Black,
# }
class FreeText:
    def __init__(self, id: str, text: str, color: tuple, rect: tuple, opacity: float):
        self.id = id
        self.pos = [rect.x0, rect.y0]
        self.size = [rect.width, rect.height]
        self.text = text
        self.color = [int(x * 255) for x in color]
        self.opacity = opacity
        
        # Styles [e.g. {'family': 'Arial', 'size': '12pt', ..., 'align': 'left', 'valign': 'top'}]
        # self.font = {style.split(":")[0][5:] : style.split(":")[1][:-1] for style in styles.split() if style[:5] != "color"}
        self.text_font = QFont()
        # self.text_font.setFamily(self.font["family"])

        # self.text_font.setStyle(FONT_STYLES[self.font["style"]])
        # self.text_font.setWeight(FONT_WEIGHTS[self.font["weight"]])

    def colliderect(self, rect: QRect | QRectF) -> bool:
        left = self.pos[0]
        top = self.pos[1]
        right = left + self.size[0]
        bottom = top + self.size[1]

        if left > rect.right():
            return False
        if right < rect.left():
            return False
        if top > rect.bottom():
            return False
        if bottom < rect.top():
            return False
        
        return True
    
    def draw(self, painter: QPainter, zoom: float):
        color = QColor(*self.color)

        pen = painter.pen()
        pen.setColor(color)
        painter.setPen(pen)

        pos = QPointF(*self.pos) * zoom
        self.text_font.setPointSizeF(self.size[1] * zoom)

        painter.setFont(self.text_font)
        painter.drawText(pos, self.text)

class Line:
    def __init__(self, id: str, points: list, color: tuple, width: int, opacity: float):
        self.id = id
        self.p1 = list(points[0])
        self.p2 = list(points[1])
        self.color = [int(c * 255) for c in color]
        self.opacity = opacity
        self.width = width

    def colliderect(self, rect: QRect | QRectF) -> bool:
        left = self.p1[0]
        right = self.p2[0]
        if left > right: left, right = right, left
        top = self.p1[1]
        bottom = self.p2[1]
        if top > bottom: top, bottom = bottom, top

        if left > rect.right():
            return False
        if right < rect.left():
            return False
        if top > rect.bottom():
            return False
        if bottom < rect.top():
            return False
        
        return True

    def draw(self, painter: QPainter, zoom: float):
        p1 = QPoint(int(self.p1[0]), int(self.p1[1])) * zoom
        p2 = QPoint(int(self.p2[0]), int(self.p2[1])) * zoom
        color = QColor(*self.color, int(self.opacity * 255))
        painter.setPen(QPen(color, self.width * zoom, Qt.PenStyle.SolidLine))
        painter.drawLine(p1, p2)

def bbox(a: QPointF, b: QPointF):
    # Finds bbox of start and end points
    left = a.x()
    right = b.x()
    if left > right:
        left, right = right, left
    top = a.y()
    bottom = b.y()
    if top > bottom:
        top, bottom = bottom, top

    return left, top, right - left, bottom - top

def colliderect(start: QPointF, end: QPointF, pos: QPointF) -> bool:
    left, top, width, height = bbox(start, end)
    right = left + width
    bottom = top + height

    # Do intersection
    x, y = pos.x(), pos.y()
    if x < left or x > right:
        return False
    if y < top or y > bottom:
        return False
    
    return True

class Stroke:
    def __init__(self, color: tuple, width: int,
                 points: list[QPointF] = None, opacity: float = 1,
                 highlight: bool = False, imported: bool = False, id: str | None = None):
        self.left = 0
        self.right = 0
        self.top = 0
        self.bottom = 0
        self.width = width

        self.id = id
        if id is None:
            self.id = uuid4()

        self.highlight = highlight
        self.color = color
        self.opacity = opacity

        self.imported = imported

        self.points: list[QPointF] = []
        if points is not None:
            for point in points:
                self.add(point)

    def add(self, pos: QPoint | QPointF):
        self.points.append(QPointF(pos))
        x, y = pos.x(), pos.y()

        # Update bounding box
        if self.right - self.left == 0:
            self.left = x
            self.top = y
            self.right = x + 5
            self.bottom = y + 5 # Default value so that a point can also be erased

        if x < self.left:
            self.left = x
        elif x > self.right:
            self.right = x
        if y < self.top:
            self.top = y
        elif y > self.bottom:
            self.bottom = y

    @property
    def rect(self) -> tuple:
        return (self.left, self.top, self.right - self.left, self.bottom - self.top)

    def collidepoint(self, pos: QPoint | QPointF) -> bool:
        x, y = pos.x(), pos.y()

        # Rect collision
        if x < self.left or x > self.right:
            return False
        if y < self.top or y > self.bottom:
            return False
        
        # Rect collision for all line segments
        for i in range(len(self.points) - 1):
            start = self.points[i]
            end = self.points[i + 1]
            if colliderect(start, end, pos):
                break
        else:
            return False

        return True

    def collideline(self, line: QLine | QLineF) -> bool:
        if type(line) != QLineF:
            line = QLineF(line)

        if not intersect_line_rect(line, QRectF(*self.rect)):
            return False

        for i in range(len(self.points) - 1):
            line2 = QLineF(self.points[i], self.points[i + 1])
            if intersect_lines(line, line2):
                return True
            
        return False
    
    def colliderect(self, rect: QRect | QRectF) -> bool | list[QLineF]:
        if self.left > rect.right():
            return False
        if self.right < rect.left():
            return False
        if self.top > rect.bottom():
            return False
        if self.bottom < rect.top():
            return False
        
        lines = []
        for i in range(len(self.points) - 1):
            line = QLineF(self.points[i], self.points[i + 1])
            if intersect_line_rect(line, rect):
                lines.append(line)
        
        if len(lines) > 0:
            return lines
        
        return False

    def denormalise(self, point: QPoint | QPointF, size: QSize | QSizeF) -> QPointF:
        return QPointF(point.x() * size.width(), point.y() * size.height())

    def draw(self, painter: QPainter,
             width: int | None = None, opacity: float | None = None,
             zoom: float = 1, lines: list[QLineF] | None = None):
        
        if width is None:
            width = self.width

        if opacity is None:
            opacity = self.opacity

        color = QColor(*self.color[:3], int(opacity * 255))
        painter.setPen(QPen(color, width * zoom, Qt.PenStyle.SolidLine))

        # Highlight stroke
        if self.highlight:
            painter.setBrush(QBrush(color))
            points = [point * zoom for point in self.points]
            polygon = QPolygonF(points)
            painter.drawPolygon(polygon, Qt.FillRule.OddEvenFill)
            return

        # Normal stroke
        # if lines is None:
        #     lines = []
        #     for i in range(len(self.points) - 1):
        #         p1 = self.points[i] * zoom
        #         p2 = self.points[i + 1] * zoom
        #         lines.append(QLineF(p1, p2))
        # else:
        #     for line in lines:
        #         line.setP1(line.p1() * zoom)
        #         line.setP2(line.p2() * zoom)
        # painter.drawLines(lines)

        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        path = QPainterPath(self.points[0] * zoom)
        for point in self.points[1:]:
            path.lineTo(point * zoom)

        painter.drawPath(path)

    def export(self):
        ...
        # points = []
        # for point in self.points:
        #     points.append(point.x())
        #     points.append(point.y())

        # creation_date = datetime.now().strftime("D:%Y%m%d%H:%M+%S+10'00\"")
        # unique_identifier = str(uuid4())

        # info = {
        #     "/BS": {'/CustomBorderStyle': '/None', '/S': '/S', '/W': self.width},
        #     "/C": [c / 255 for c in self.color],
        #     "/CA": self.opacity,
        #     "/Rect": [self.left, self.top, self.right, self.bottom],
        #     "/Type": "/Annot",
        #     "/Subtype": "/Ink",
        #     "/InkList": [points]
        # }

        #<</BM/Multiply/CA 0.501961/ca 0.501961>>
        # if self.highlight:
        #     info['/BM'] = '/Multiply'
        #     info["/ca"] = self.opacity
        #     info['/BE'] = {'/I': 0, '/S': '/S'}
        #     info['/Contents'] = ''
        #     info["/FillOpacity"] = 0
        #     info["/F"] = 4
        #     info["/IC"] = [0, 0, 0]
        #     info["/Subj"] = ''
        #     info["/ca"] = 0
        #     info["/Rotation"] = 0
        #     info["/HatchTileSize"] = 0 
        #     info["/HatchRotation"] = 0 
        #     info["/HatchColor"] = 0 
        #     info["/HatchPatternName"] = 'None'

        # return info

        # info = {
        #     "/AP": {'/N': None}, # {'/N': IndirectObject(17, 0, 2682469479312)}
        #     "/BE": {'/I': 0, '/S': '/S'},
        #     "/BM": '/Normal', 
        #     "/BS": {'/CustomBorderStyle': '/None', '/S': '/S', '/W': self.width},
        #     "/C": [c / 255 for c in self.color],
        #     "/CA": self.opacity,
        #     "/Contents": '',
        #     "/CreationDate": creation_date, # "D:20240828115610+10'00"
        #     "/F": 4,
        #     "/FillOpacity": 0,
        #     "/HatchColor": '0',
        #     "/HatchPatternName": 'None',
        #     "/HatchRotation": 0,
        #     "/HatchTileSize": 0,
        #     "/IC": [0, 0, 0],
        #     "/InkList": [points], # Double listed for some reason
        #     "/M": creation_date, # "D:20240828115605+10'00"
        #     "/NM": unique_identifier, # UUID string - 'a2d3cf49-fc5d-4204-82e5-a1e443db16a7'
        #     "/P": None, # IndirectObject(10, 0, 2682469479312)
        #     "/Rect": [self.left, self.top, self.right, self.bottom],
        #     "/Rotation": 0,
        #     "/Subj": '',
        #     "/Subtype": '/Ink',
        #     "/T": None, # 'robbing chew'
        #     "/Type": '/Annot',
        #     "/ca": 0
        # }

def intersect_lines(line1: QLineF, line2: QLineF):
    x0, y0 = line1.x1(), line1.y1()
    x1, y1 = line1.x2(), line1.y2()
    x2, y2 = line2.x1(), line2.y1()
    x3, y3 = line2.x2(), line2.y2()

    s1_x = x1 - x0
    s1_y = y1 - y0
    s2_x = x3 - x2
    s2_y = y3 - y2

    d = -s2_x * s1_y + s1_x * s2_y
    if d == 0: # Dot product is 0, lines are parallel
        # Check for collinearity
        if x1 == 0 or y1 == 0:
            return x2 * y1 != y2 * x1
        elif x2 == 0:
            return y1 != 0
        else:
            return y1 / x1 == y2 / x2
        
    s = (-s1_y * (x0 - x2) + s1_x * (y0 - y2)) / d
    t = ( s2_x * (y0 - y2) - s2_y * (x0 - x2)) / d

    if (s >= 0 and s <= 1 and t >= 0 and t <= 1):
        return True
    
    return False

def intersect_line_rect(line: QLineF, rect: QRectF):
    x1, y1 = line.x1(), line.y1()
    x2, y2 = line.x2(), line.y2()
    left, top, right, bottom = rect.getCoords()
    
    # Return False if both endpoints are confidently outside of rect
    if x1 < left and x2 < left:
        return False
    if x1 > right and x2 > right:
        return False
    if y1 < top and y2 < top:
        return False
    if y1 > bottom and y2 > bottom:
        return False
    
    # Return True if both endpoints are inside of the rect
    if x1 >= left and x1 <= right and y1 >= top and y1 <= bottom:
        if x2 >= left and x2 <= right and y2 >= top and y2 <= bottom:
            return True
        
    # Intersect with all four sides
    p1 = QPointF(left, top)
    p2 = QPointF(right, top)
    p3 = QPointF(right, bottom)
    p4 = QPointF(left, bottom)

    if intersect_lines(line, QLineF(p1, p2)): return True
    if intersect_lines(line, QLineF(p2, p3)): return True
    if intersect_lines(line, QLineF(p3, p4)): return True
    if intersect_lines(line, QLineF(p4, p1)): return True

    return False

if __name__ == "__main__":
    s = Stroke((0, 0, 0), 1, [QPointF(0, 0), QPointF(50, 50)])
    rect = QRectF(40, 0, 30, 30)
    print(s.colliderect(rect))