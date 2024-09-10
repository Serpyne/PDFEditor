import pymupdf

pdf_path = r"C:\Users\CHE0307\Downloads\Newton II prac (PASCO Smart Cart) 2024 (1).pdf"

doc = pymupdf.open(pdf_path)
pages = [page for page in doc.pages()]
print(pages[0].get_images())
xref = pages[0].get_image_info(xrefs=True)

data = doc.extract_image(220)
with open("output.png", "wb") as f:
    f.write(data["image"])