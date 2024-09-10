from PyQt5.QtGui import QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from time import perf_counter
import sys

RESOLUTION = 1280, 720
NUM_UNDOS = 25

# def dist_to_point(self, pos):
#     norm(np.cross([p2[0] - p1[0], p2[1] - p1[1]], [p1[0] - p3[0], p1[1] - p3[1]])) / norm([p2[0] - p1[0], p2[1] - p1[1]])

class DrawingPanel(QWidget):
    def __init__(self, parent, size: tuple):
        super(DrawingPanel, self).__init__(parent)

        self.image = QImage(QSize(*size), QImage.Format_RGB32)
        self.image.fill(Qt.white)

        self.painter = QPainter(self.image)
        self.painter.setRenderHints(QPainter.Antialiasing)

        self.pen_color = 50, 50, 50
        self.pen_width = 3
        self.pen = QPen(QColor.fromRgb(*self.pen_color), self.pen_width, Qt.SolidLine)
        self.painter.setPen(self.pen)
        
        self.update()

        self.strokes = []
        self.previous_point = None
        self.drawing = False

        self.erasing = False
        self.erased_strokes = []
        self.erase_action = {}

        # self.resizeEvent

        # self.buffer = 0
        # self.prev = 0

    def paintEvent(self, event):
        canvasPainter = QPainter(self)
        canvasPainter.drawImage(self.rect(), self.image, self.image.rect())
        event.accept()

    def setColor(self, color: tuple | QColor):
        if type(color) == QColor:
            self.pen_color = (*QColor.getRgb(), 255)
        elif type(color) == tuple:
            if len(color) == 3:
                self.pen_color = (*color, 255)
            elif len(color) > 3:
                self.pen_color = color[:4]

        self.pen = QPen(QColor(*self.pen_color), self.pen_width, Qt.SolidLine)
        self.painter.setPen(self.pen)

    def tabletEvent(self, event: QTabletEvent):
        # > IDK HOW TO DETECT THE BOTTOM BUTTON???
        # if event.type() != QEvent.Type.TabletRelease:
        # print(bool(event.buttons() & Qt.MouseButton.LeftButton))
        # if event.buttons() & Qt.MouseButton.LeftButton:
        #     self.prev = perf_counter()
        # else:
        #     dt = perf_counter() - self.prev
        #     print(dt)
            
        # Detects top stylus button press
        self.erasing = False
        if event.buttons() & Qt.MouseButton.RightButton:
            self.erasing = True

        # w_ratio = self.width() / self.drawingPanel.width()
        # h_ratio = self.parent().height() / self.height()
        # print(self.parent().size(), self.size())

        ratio = self.image.height() / self.height()
        pos = event.pos() * ratio
        # pressure = event.pressure()
        if self.erasing:
            self.drawing = False

            for i, stroke in enumerate(self.strokes):
                if stroke.collidepoint(pos):
                    if i not in self.erase_action:
                        self.erase_action[i] = stroke
                        stroke.draw(self.painter, width=12, opacity=0.3)
                        self.update()

            return

        match event.type():
            case QEvent.Type.TabletPress:
                self.strokes.append(Stroke(self.pen_color))
                self.previous_point = pos
                self.drawing = True

            case QEvent.Type.TabletMove:
                # self.strokes[-1].append({"pos": pos, "pressure": pressure})
                if len(self.strokes) == 0:
                    self.drawing = False
                if self.drawing:
                    self.strokes[-1].add(pos)
                    self.setColor(self.strokes[-1].color)
                    self.painter.drawLine(pos, self.previous_point)
                    self.previous_point = pos

            case QEvent.Type.TabletRelease:
                if len(self.erase_action) > 0:
                    self.erased_strokes.append(list(self.erase_action.values()))

                    for action in self.erased_strokes:
                        for stroke in action:
                            if stroke in self.strokes:
                                self.strokes.remove(stroke)
                    self.refresh()
    
                    self.erase_action = {}
                    # Make sure length of erased_strokes <= number of undos
                    self.erased_strokes = self.erased_strokes[-min(NUM_UNDOS, len(self.erased_strokes)):]

            case _:
                pass

        self.update()
        event.accept()

    def refresh(self):
        self.image.fill(Qt.white)
        for stroke in self.strokes:
            stroke.draw(self.painter, width=self.pen_width)
        self.update()

class Window(QWidget):
    def __init__(self):
        super(Window, self).__init__()

        self.resize(*RESOLUTION)
        self.drawingPanel = DrawingPanel(self, (720, 1280))

        self.setWindowTitle('Review')
        self.show()

        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.undo)

    def resizeEvent(self, event):
        size = event.size()
        height = size.height()
        width = height * 9 // 16
        self.drawingPanel.setFixedSize(QSize(width, height))
    
    def undo(self):
        if len(self.erased_strokes) > 0:
            for stroke in self.erased_strokes[-1]:
                self.strokes.append(stroke)
        
            self.erased_strokes.pop(-1)
            self.refresh()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = Window()

    sys.exit(app.exec())
