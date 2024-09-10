from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
import sys
import re

from time import perf_counter
from colorsys import hsv_to_rgb, rgb_to_hsv

import pymupdf
from pypdf import PdfWriter, PdfReader
from pypdf.generic import PdfObject
from struct import pack

from reader import Reader
from classes import *

RESOLUTION = 1920, 1080
NUM_UNDOS = 25

USERNAME = 'Robin'

class GraphicsArea(QGraphicsView):
    def __init__(self, parent, size):
        super(QGraphicsView, self).__init__(parent)

        # self.grabGesture(Qt.GestureType.TapAndHoldGesture) # Long touch gesture
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        
        self._scene = QGraphicsScene()
        self.setScene(self._scene)

        # Canvas image
        self.pen_color = 0, 0, 0
        self.pen_width = .5
        self.background_color = QColor(220, 220, 220)
        self.aspect_ratio = size[0] / size[1]

        self.original_size = QSize(*size)
        self.image_size = QSize(*size)
        self.image = QImage(self.image_size, QImage.Format.Format_RGB32)
        self.image.fill(self.background_color)

        self.painter = QPainter(self.image)
        self.painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.pen = QPen(QColor.fromRgb(*self.pen_color), self.pen_width, Qt.PenStyle.SolidLine)
        self.painter.setPen(self.pen)
        
        self.strokes: list[Stroke] = []
        self.previous_point = None
        self.drawing = False

        self.objects: list[Square, FreeText, Line] = []

        self.erasing = False
        self.erased_strokes = {}
        
        # Canvas position and scale
        self.offset = QPointF(0, 0)
        self.drawRect = QRect(0, 0, 0, 0)

        self.old_touch_pos = QPointF(0, 0)

        self.old_zoom = 1
        self.zoom = 1
        self.zoom_center = QPointF(self.width() // 2, self.height() // 2)
        self.pinching = False

        self.max_zoom = 18
        self.min_zoom = .5

        self.actions_stack = []

        # TEST: Create a bunch of diagonal lines to test performance of erasing 
        # dy = size[1] / 150
        # for i in range(100):
        #     self.strokes.append(Stroke(self.pen_color, self.pen_width, points=[QPointF(10 + i * 3 + x, 10 + x * dy) for x in range(50)]))
        # self.refresh()

    def event(self, event: QEvent) -> bool:
        # print(event.type() in [QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd, QEvent.Type.TouchCancel])
        match event.type():
            case QEvent.Type.Show:
                self.offset = QPointF(self.width(), self.height()) / 2
                self.reset_painter()
                self.refresh()
            case QEvent.Type.Gesture:
                return self.gestureEvent(QGestureEvent(event))
            case QEvent.Type.TouchBegin:
                return self.touchBeginEvent(event)
            case QEvent.Type.TouchUpdate:
                return self.touchUpdateEvent(event)
            case QEvent.Type.TouchEnd:
                return self.touchEndEvent(event)
            
        result = QGraphicsView.event(self, event)
        return result
    
    def resizeEvent(self, event: QResizeEvent):
        rel_size = event.size() - event.oldSize()
        self.offset += QPointF(rel_size.width(), rel_size.height()) / 2
        
        self.refresh()

    def gestureEvent(self, event: QGestureEvent):
        gesture = event.gestures()[0]
        self.pinchTriggered(gesture)

        return True

    def pinchTriggered(self, gesture: QPinchGesture):
        # Two-finger pinch gesture event
        center = self.mapFromGlobal(gesture.centerPoint())
        rel_pos = center - self.mapFromGlobal(gesture.lastCenterPoint())
        scale = gesture.scaleFactor()
        # angle = gesture.rotationAngle()

        self.zoom = min(self.max_zoom, max(self.min_zoom, self.zoom * scale))
        self.offset += rel_pos / self.zoom

        # Is called once at the start of a pinch gesture.
        # This performs the zooming into the midpoint between the two gesture fingers
        if not self.pinching:
            self.zoom_center = self.mapFromGlobal(gesture.centerPoint())

            before = self.drawRect.center()
            after = (self.offset - self.zoom_center) * self.zoom + self.zoom_center

            diff = before.toPointF() - after
            self.offset += diff / self.zoom

        self.pinching = True
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        self.previous_point = event.globalPosition()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.previous_point is None:
            return
        pos = event.globalPosition()
        rel_pos = pos - self.previous_point
        self.offset += rel_pos / self.zoom
        self.update()
        self.previous_point = pos

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.previous_point = None
        event.accept()

    def reset_painter(self):
        height = self.original_size.height()
        width = int(height * self.aspect_ratio)
        self.image_size = QSize(int(width * self.zoom), int(height * self.zoom))

        self.painter.end()
        self.image = QImage(self.image_size, QImage.Format.Format_RGB32)
        self.image.fill(self.background_color)
        self.painter = QPainter(self.image)
        self.painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    def touchBeginEvent(self, event: QTouchEvent):
        self.old_touch_pos = event.point(0).position()
        event.accept()
        return True

    def touchUpdateEvent(self, event: QTouchEvent):
        # Called only if one finger is used
        if self.pinching:
            event.accept()
            return False
        
        pos = event.point(0).position()
        rel_pos = pos - self.old_touch_pos
        self.old_touch_pos = pos
        
        self.offset += rel_pos / self.zoom
        self.update()

        event.accept()
        return True

    def touchEndEvent(self, event: QTouchEvent):
        self.pinching = False
        
        # Every time the zoom changes, each stroke must be re-rasterised.
        if self.old_zoom != self.zoom:
            self.reset_painter()
            self.old_zoom = self.zoom

        self.refresh()

        event.accept()
        return True

    def drawForeground(self, qp, rect):
        qp.save()
        qp.resetTransform()

        # Draw canvas to GraphicsView
        height = self.original_size.height()
        width = int(height * self.aspect_ratio)

        center = (self.offset - self.zoom_center) * self.zoom + self.zoom_center
        self.image_size = QSize(int(width * self.zoom), int(height * self.zoom))
        self.drawRect = QRect()
        self.drawRect.setSize(self.image_size)
        self.drawRect.moveCenter(center.toPoint())
        qp.drawImage(self.drawRect, self.image, self.image.rect())
        qp.restore()

    def screen_to_canvas(self, pos: QPointF) -> QPointF:
        ratio = self.image.height() / self.original_size.height()
        return (pos - self.drawRect.topLeft().toPointF()) * ratio / self.zoom

    def canvas_to_screen(self, pos: QPointF) -> QPointF:
        ratio = self.image.height() / self.original_size.height()
        return pos * self.zoom / ratio + self.drawRect.topLeft().toPointF()

    def setColor(self, color: tuple):
        self.pen_color = [int(c) for c in color]
        self.pen = QPen(QColor(*self.pen_color), self.pen_width, Qt.PenStyle.SolidLine)
        self.painter.setPen(self.pen)

    def setWidth(self, width: int):
        self.pen_width = width
        self.pen = QPen(QColor(*self.pen_color), self.pen_width, Qt.PenStyle.SolidLine)
        self.painter.setPen(self.pen)

    def eraseEvent(self, pos: QPointF):
        if self.previous_point is None:
            self.previous_point = pos
            return
        
        self.drawing = False

        line = QLineF(self.previous_point / self.zoom, pos / self.zoom)
        for i, stroke in enumerate(self.strokes):
            if stroke.collideline(line):
                if i not in self.erased_strokes:
                    self.erased_strokes[i] = stroke
                    stroke.draw(self.painter, width=5, opacity=0.2, zoom=self.zoom)

        self.update()
        self.previous_point = pos

    def normalise(self, point: QPoint | QPointF) -> QPointF:
        return QPointF(point.x() / self.image_size.width(), point.y() / self.image_size.height())

    def denormalise(self, point: QPoint | QPointF) -> QPointF:
        return QPointF(point.x() * self.image_size.width(), point.y() * self.image_size.height())

    def tabletPressEvent(self, pos: QPointF):
        self.strokes.append(Stroke(self.pen_color, self.pen_width))
        self.previous_point = pos
        self.drawing = True

    def tabletMoveEvent(self, pos: QPointF):
        if len(self.strokes) == 0:
            self.drawing = False
        if self.drawing:
            self.strokes[-1].add(pos / self.zoom)
            self.painter.setPen(QPen(QColor(*self.strokes[-1].color), self.pen_width * self.zoom, Qt.PenStyle.SolidLine))
            self.painter.drawLine(pos, self.previous_point)
            self.previous_point = pos

    def tabletReleaseEvent(self, pos: QPointF):
        self.previous_point = None
        if len(self.erased_strokes) > 0:
            self.actions_stack.append(list(self.erased_strokes.values()))

            for action in self.actions_stack:
                for stroke in action:
                    if stroke in self.strokes:
                        self.strokes.remove(stroke)
            self.refresh()

            self.erased_strokes = {}

            # Make sure length of erased_strokes <= number of undos
            # self.actions_stack = self.actions_stack[-min(NUM_UNDOS, len(self.actions_stack)):]

    def handleTablet(self, event: QTabletEvent = None, pos: QPointF = None):
        # Tablet-Stylus press, move and release events
        if event.pointerType() == QPointingDevice.PointerType.Eraser:
            self.eraseEvent(pos)
        match event.type():
            case QEvent.Type.TabletPress:
                self.tabletPressEvent(pos)
            case QEvent.Type.TabletMove:
                self.tabletMoveEvent(pos)
            case QEvent.Type.TabletRelease:
                self.tabletReleaseEvent(pos)

    def tabletEvent(self, event: QTabletEvent):
        # Calculate relative cursor position
        pos = self.screen_to_canvas(event.position())

        # Return if cursor is outside of canvas bounds
        # if pos.x() < 0 or pos.x() > self.image.width() or pos.y() < 0 or pos.y() > self.image.height():
        #     return

        # Detects top stylus button press
        self.erasing = False
        if event.buttons() & Qt.MouseButton.RightButton:
            if len(self.strokes[-1].points) > 0:
                self.strokes.append(Stroke(self.pen_color, self.pen_width))
                self.previous_point = None
            self.erasing = True

        # If erase button is held down, all selected strokes will be deleted
        if self.erasing:
            self.eraseEvent(pos)
            return

        self.handleTablet(event, pos)

        # Update screen
        self.update()
        event.accept()

    def update(self):
        # Update QGraphicsView.drawForeground() call
        QGraphicsView.update(self)
        self.scene().invalidate()

    def refresh(self):
        self.image.fill(self.background_color)

        topleft = self.screen_to_canvas(QPointF(0, 0)) / self.zoom
        bottomright = self.screen_to_canvas(QPointF(self.width(), self.height())) / self.zoom
        clipping_rect = QRectF(topleft, bottomright)

        for stroke in self.strokes:
            lines = stroke.colliderect(clipping_rect)
            if lines:
                stroke.draw(self.painter, lines=lines, zoom=self.zoom)

        for object in self.objects:
            lines = object.colliderect(clipping_rect)
            if lines:
                object.draw(self.painter, zoom=self.zoom)

        self.update()

    def add_stroke(self, object: Ink):
        points = [QPointF(point[0], point[1]) for point in object.points]
        color = object.color
        width = object.width
        highlight = object.highlight
        opacity = object.opacity
        self.strokes.append(Stroke(color, width, points, opacity, highlight, imported=True)) 

    def add_rect(self, object: Square):
        self.objects.append(object)

    def add_text(self, object: FreeText):
        self.objects.append(object)

    def add_line(self, object: Line):
        self.objects.append(object)

class ColorPicker(QWidget):
    def __init__(self, parent, size: tuple, initial_color: tuple = (0, 0, 0), *args, **kwargs):
        super(ColorPicker, self).__init__(parent, *args, **kwargs)

        menu_widget = QListWidget()
        for i in range(10):
            item = QListWidgetItem(f"Item {i}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            menu_widget.addItem(item)

        layout = QHBoxLayout()

        self.selected_color = initial_color
        hsv = rgb_to_hsv(*[c / 255 for c in initial_color])

        container = QHBoxLayout()
        layout.addLayout(container)

        self.image_size = QSize(50, 50)
        self.canvas_size = size

        self.canvas_image = QImage(self.image_size, QImage.Format.Format_RGB32)
        self.canvas_image.fill(QColor(255, 255, 255))
        self.label = QLabel()
        container.addWidget(self.label)

        self.slider = QSlider(Qt.Orientation.Vertical, self)
        self.slider.setMinimum(0)
        self.slider.setMaximum(360)
        self.slider.setValue(int(hsv[0] * 360))
        self.color_value = self.slider.value()
        self.slider.setTickInterval(1)
        self.slider.valueChanged.connect(self.sliderChangeEvent)
        self.slider.sliderReleased.connect(self.draw)
        styles = 'QSlider::groove:vertical { border-image: url(hue-map.png) 0 0 0 0 stretch stretch; position: absolute; left: 8px; right: 7px; width: 12px; height: ' + str(self.canvas_size[1]) + '; }'
        styles += "QSlider::handle:vertical { height: 8px; background: #979EA8; margin: 0 -4px; border-style:solid; border-color: grey; border-width:1px; border-radius:3px; }"
        self.slider.setStyleSheet(styles)
        layout.addWidget(self.slider)

        self.setLayout(layout)
        self.label.setFixedSize(*size)
        self.setMinimumSize(self.canvas_size[0] + 50, self.canvas_size[1] + 50)

        self.pressed = True
        self.mouse_pos = QPoint(int(hsv[1] * size[0]), size[1] - int(hsv[2] * size[1]))
        
        self.draw()

    def update_color(self):
        x = self.mouse_pos.x() / self.canvas_size[0]
        y = 1 - self.mouse_pos.y() / self.canvas_size[1]
        rgb = hsv_to_rgb(self.color_value / 360, x, y)
        self.selected_color = [c * 255 for c in rgb]
        self.parent().penColorChangedEvent(self.selected_color)

    def mousePressEvent(self, event: QMouseEvent):
        self.mouse_pos = self.label.mapFromGlobal(event.pos())
        self.update_color()
        self.pressed = True
        self.draw_cursor()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.pressed:
            return
        
        self.mouse_pos = self.label.mapFromGlobal(event.pos())
        self.mouse_pos.setX(max(0, min(self.canvas_size[0], self.mouse_pos.x())))
        self.mouse_pos.setY(max(0, min(self.canvas_size[1], self.mouse_pos.y())))
        self.update_color()

        self.draw_cursor()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.pressed = False
        event.accept()

    def sliderChangeEvent(self):
        self.color_value = self.slider.value()
        self.update_color()
        # self.draw()

    def draw(self):
        width = self.image_size.width()
        height = self.image_size.height()

        ptr = self.canvas_image.bits()
        ptr.setsize(self.canvas_image.sizeInBytes())
        arr = ptr.asarray()

        for y in range(height):
            for x in range(width):
                index = ((height - y - 1) * width + x) * 4 # 4 bytes per pixel
                rgb = hsv_to_rgb(self.color_value / 360, x / width, y / height)
                # BGR Color Format
                arr[index] = int(rgb[2] * 255)
                arr[index + 1] = int(rgb[1] * 255)
                arr[index + 2] = int(rgb[0] * 255)

        self.draw_cursor()
        self.label.adjustSize()

    def draw_cursor(self):
        image = self.canvas_image.scaled(*self.canvas_size)
        qp = QPainter(image)
        qp.setBrush(QColor(255, 255, 255))
        qp.drawEllipse(self.mouse_pos, 4, 4)
        qp.end()
        pixmap = QPixmap.fromImage(image)
        self.label.setPixmap(pixmap)

class Window(QMainWindow):
    def __init__(self, filename: str):
        super(QMainWindow, self).__init__()
        # self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.FramelessWindowHint)

        self.resize(*RESOLUTION)
        self.setWindowTitle('Editor')

        self.filename = filename
        self.reader = Reader(filename)
        if len(self.reader.objects) == 0:
            print("Document is not readable")
            sys.exit()

        page_size = [int(x) for x in self.reader.page_info[0]["size"]]
        self.gv = GraphicsArea(self, page_size)
        self.setCentralWidget(self.gv)

        self.colorpicker = ColorPicker(self, (300, 300))

        self.load_page()

        self.show()

        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save)
        
        exit_shortcut = QShortcut(QKeySequence("Escape"), self)
        exit_shortcut.activated.connect(self.closeEvent)

    def penColorChangedEvent(self, color: tuple):
        self.gv.setColor(color)

    def closeEvent(self, event: QCloseEvent | None = None):
        self.save()
        self.close()

    def save(self, save_filename: str = None):
        if save_filename is None:
            save_filename = self.filename
            
        doc = pymupdf.open()
        page = doc.new_page()

        # Append strokes
        for stroke in self.gv.strokes:
            points = [(point.x(), point.y()) for point in stroke.points]
            color = [c / 255 for c in stroke.color]

            annot = page.add_ink_annot([points])
            annot.set_border(width=stroke.width)
            annot.set_colors(stroke=color)
            annot.set_opacity(stroke.opacity)
            annot.update()
            if stroke.highlight:
                annot.update(fill_color=color)

        # Append objects
        for object in self.gv.objects:
            # WRITE OBJECTS TO 'writer'
            match object:
                case Square():
                    rect = (*object.pos, object.pos[0] + object.size[0], object.pos[1] + object.size[1])
                    border_color = [c / 255 for c in object.border_color]
                    fill_color = [c / 255 for c in object.fill_color]

                    annot = page.add_rect_annot(rect)
                    annot.set_colors(stroke=border_color, fill=fill_color)
                    # annot.set_opacity(object.opacity)
                    annot.set_border(width=object.border_width)
                    ...
                case FreeText():
                    ...
                case Line():
                    ...
                case _:
                    ...
            annot.update()
            object.nm = annot.info["id"]

        page_objects = {page_num: {annot.info["id"]: annot.xref for annot in page.annots()} for page_num, page in enumerate(doc.pages())}

        def replace_attr(obj_str: str, match_string: str, replace_string: str) -> str:
            match = re.search(match_string, obj_str)
            if not match:
                return obj_str
            
            return obj_str[:match.start()] + replace_string + obj_str[match.end():]
            
            
        def get_form_of_annot(match_xref: int) -> bytes | None:
            xreflen = doc.xref_length() # number of objects in file
            for xref in range(1, xreflen): # skip item 0!
                if xref == match_xref + 1:
                    # if stream := doc.xref_stream(xref):
                    return doc.xref_stream(xref)
                        # stream = replace_attr(stream, b"\n(.+?) RG", b"\n0 0 1 RG")
                        # doc.update_stream(xref, stream)

        for object in self.gv.objects:
            match object:
                case Square():
                    # rect["/NM"] = object.id
                    # rect["/FillOpacity"] = object.opacity
                    # rect["/C"] = [1, 0, 0]
                    # for page in page_objects:
                    #     objects = page_objects[page]
                    #     if not object.nm:
                    #         continue

                    # fill_color = " ".join([str(c / 255) for c in object.fill_color])
                    # border_color = " ".join([str(c / 255) for c in object.border_color])

                    # xref = objects[object.nm]
                    # stream = get_form_of_annot(xref)
                    # print(doc.xref_object(xref))

                    # fill_color = [pack("f", c / 255) for c in object.fill_color]
                    # print(fill_color)

                    # replace_bytes = b"\n" + b" ".join(fill_color) + b" RG"
                    # stream = replace_attr(stream, b"\n(.+?) RG", replace_bytes)
                    # doc.update_stream(xref + 1, stream)
                    # obj = doc.xref_object(xref, 1)
                    # print(obj)

                    # obj = replace_attr(obj, "/C\[.+?\]", f"/C[{border_color}]")
                    # obj = replace_attr(obj, "/IC\[.+?\]", f"/IC[{fill_color}]")
                    # obj = replace_attr(obj, "/NM\(.+?\)", f"/NM({object.id})")



                    # doc.update_object(xref, obj)
                    ...
                case _:
                    ...

        doc.save(save_filename)
        # reader = PdfReader(save_filename)
        # for annot in reader.pages[0]["/Annots"]:
        #     obj = annot.get_object()
        #     if obj["/Subtype"] == "/Square":
        #         print(obj)

        # objects = {page_num : [a.get_object() for a in page["/Annots"]] for page_num, page in enumerate(writer.pages)}
        # objects = objects[0] # first page, fix later for multiple pages
        
        # def get_obj_by_nm(obj_nm: str):
        #     for annot_obj in objects:
        #         if annot_obj["/NM"] == obj_nm:
        #             return dict(annot_obj)
                
        #     return None

        # writer = PdfWriter()
        # reader = PdfReader(save_filename)
        # for page in reader.pages:
        #     writer.add_page(page)

        # for object in self.gv.objects:
        #     match object:
        #         case Square():
        #             rect = get_obj_by_nm(object.nm)
        #             rect["/NM"] = object.id
        #             rect["/FillOpacity"] = object.opacity
        #             rect["/C"] = [1, 0, 0]
        #             print(rect)
        #             writer.add_annotation(0, rect)
        #         case _:
        #             ...

        # writer.write(save_filename)

    def process_object(self, object):
        match object:
            case Ink():
                self.gv.add_stroke(object)
            case Square():
                self.gv.add_rect(object)
            case FreeText():
                self.gv.add_text(object)
            case Line():
                self.gv.add_line(object)
            case _:
                ...

    def load_page(self, page_num: int = 0) -> Reader:
        page_objects = self.reader.objects[page_num]
        for object in page_objects:
            self.process_object(object)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = Window("test.pdf")

    sys.exit(app.exec())
