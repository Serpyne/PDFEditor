import pymupdf
import pymupdf.extra
from classes import *
from pypdf import PdfReader

class Reader:
    def __init__(self, filename):
        super().__init__()

        self.filename = filename

        self.page_info = {}
        self.objects = {}

        self.ghost_reader = PdfReader(filename)

        self.read_annotations()

        self.ghost_reader.close()

    def read_annotations(self):
        self.doc = pymupdf.open(self.filename)

        self.objects = {}
        for i, page in enumerate(self.doc):
            rect = page.cropbox
            self.page_info[i] = {"size": [rect.width, rect.height]}

            self.objects[i] = []
            for annot in page.annots():
                self.add_annotation(i, annot)

        self.doc.close()

    def add_annotation(self, page_num: int, obj: pymupdf.Annot):
        obj_id = obj.info["id"]
        match obj.type[1]:
            case "Ink":
                points = obj.vertices[0]
                color = obj.colors["stroke"]
                width = obj.border["width"]
                if width == 0: opacity = obj.opacity
                else: opacity = 1
                self.objects[page_num].append(Ink(id=obj_id, points=points, color=color, width=width, opacity=opacity))
            # case "Square":
            #     rect = obj.rect
            #     opacity = obj.opacity
            #     border_color = obj.colors["stroke"]
            #     fill_color = obj.colors["fill"]
            #     border_width = obj.border["width"]

            #     # Get FillOpacity from other PdfReader
            #     annot_id = obj.info["id"]
            #     alt_annots = [annot.get_object() for annot in self.ghost_reader.pages[page_num]["/Annots"]]
            #     for annot in alt_annots:
            #         if annot_id == annot["/NM"] and "/FillOpacity" in annot:
            #             opacity = annot["/FillOpacity"]
            #             # print(annot)

            #     self.objects[page_num].append(Square(id=obj_id, rect=rect, opacity=opacity, border_color=border_color, fill_color=fill_color, border_width=border_width))
            # case "FreeText":
            #     text = obj.info["content"]
            #     color = obj.colors["stroke"]
            #     rect = obj.rect
            #     opacity = obj.opacity
            #     self.objects[page_num].append(FreeText(id=obj_id, text=text, color=color, rect=rect, opacity=opacity))
            # case "Line":
            #     points = obj.vertices
            #     color = obj.colors["stroke"]
            #     width = obj.border["width"]
            #     opacity = obj.opacity
            #     self.objects[page_num].append(Line(id=obj_id, points=points, color=color, width=width, opacity=opacity))
            # case _:
            #     print(obj)
                # annotation = {"subtype": obj["/Subtype"], "location": obj["/Rect"]}
                # self.objects[i].append(annotation)

if __name__ == "__main__":
    Reader("test.pdf")