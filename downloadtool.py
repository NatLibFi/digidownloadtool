# -*- coding: utf-8 -*-

from tkinter import *
from tkinter.tix import *
from tkinter.ttk import *
from tkinter import filedialog
from digi_downloadcontent import DownloadContent
from PIL import Image, ImageTk
import sys
import os
import queue
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import time
from datetime import datetime
import pickle

class Application(Frame):

    def close_window(self):
        sys.exit()

    def __init__(self, master=None):
        super().__init__(master)
        self.master.title('Download tool')
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.close_window)

        self.directoryTrees = {
            "BindingTitle_BindingID": 0,
            "BindingIssn": 1,
            "BindingTitle_BindingID/year": 2,
            "BindingIssn/year": 3,
            "year/BindingIssn": 4,
            "year/BindingTitle_BindingID": 5
        }

        container = Frame(root)
        canvas = Canvas(container, highlightthickness=0)
        scrollbar = Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = Frame(canvas)

        self.win = scrollable_frame

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)

        self.create_widgets()

        self.prevFrameHeight = 0

        def on_configure(event):
            width = scrollable_frame.winfo_width()
            height = scrollable_frame.winfo_height()

            screenHeight = self.win.winfo_screenheight()

            if screenHeight > height:
                canvas.config(width=width, height=height)
                scrollable_frame.config(width=width, height=height)

                canvas.pack()
                self.pack()
            
            if self.prevFrameHeight != height:
                canvas.yview_moveto(1)

            self.prevFrameHeight = height


        root.bind('<Configure>', on_configure)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        container.pack()
        self.pack(fill="both", expand=True)

        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        scrollable_frame.bind_all("<MouseWheel>", _on_mousewheel)

        self.formatTemplates = []

        #if is resume download, add variables from resumeItems.pkl
        if os.path.exists('resumeItems.pkl'):
            with open('resumeItems.pkl', 'rb') as f:
                self.lastBindingIndex, self.lastBindingsData, self.hitsData, self.totalPagesData, self.bindingsCsvData, tempUrl,selectedOCRFormat, selectedImageFormat, saveDir, self.formatTemplates, allBindingPages, selectedTree = pickle.load(f)

                if self.lastBindingIndex != -1:
                    self.cancelDownloadButton['state'] = NORMAL
                    self.startDownloadButton.config(text="Resume download")
                    self.digiResultsUrl.insert(INSERT, tempUrl)
                    self.selectedOCRFormat.set(selectedOCRFormat)
                    self.selectedImageFormat.set(selectedImageFormat)
                    self.saveDirectoryPath.set(saveDir)
                    self.downloadAllBindingPages.set(allBindingPages)
                    self.selectedTree.set(selectedTree)

    def removeResumeItems(self):
        if os.path.exists('resumeItems.pkl'):
            os.remove('resumeItems.pkl')

    def create_widgets(self):
        self.frame_buttons = Frame(self.win)
        self.frame_buttons.grid(row = 6, column = 0, sticky = W, padx = 2, pady = 2)

        self.startDownloadButton = Button(self.frame_buttons, text="Download material", command= lambda: self.startDownloadThread(self.digiResultsUrl.get("1.0",'end-1c'), self.selectedOCRFormat.get(), self.selectedImageFormat.get(), True, self.saveDirectoryPath.get(), self.statusText, self.createKeywordsGraph, self.setDownloadResumeItems))
        self.startDownloadButton.pack(side="left")

        self.cancelDownloadButton = Button(self.frame_buttons, text="Cancel download",command= lambda: self.cancelDownload())
        self.cancelDownloadButton.pack(side="right")
        self.cancelDownloadButton['state'] = DISABLED

        self.joinExcels = StringVar()
        self.joinExcels.set("0")
        self.joinBindingsCsvDf = pd.DataFrame()
        self.joinPageCountsCsvDf = pd.DataFrame()

        self.ax1 = None
        self.bar1 = None
        self.frame_graphContent = None
        self.lastBindingIndex = -1
        self.hitsData = {}
        self.totalPagesData = {}
        self.bindingsCsvData = {}
        self.lastBindingsData = []
        
        self.downloadThreadStarted = False

        self.createStatusTextWidget()
        self.createAineistoFrame()
        self.createOCRFormatFrame()
        self.createImageFormatFrame()
        self.createDownloadBindingPagesFrame()
        self.createSaveDirectoryBrowser()
        self.createLogoFrame()

    def startDownloadThread(self, digiResultsUrl, OCRformat, imageFormat, nomaxlimit, saveDirectoryPath, statusText, createKeywordsGraph, setDownloadResumeItems):
        self.queue = queue.Queue()
        if not self.downloadThreadStarted:
            self.downloadThread = DownloadContent(self.queue, digiResultsUrl, OCRformat, imageFormat, nomaxlimit, saveDirectoryPath, statusText, createKeywordsGraph, setDownloadResumeItems, self.hitsData, self.totalPagesData, self.bindingsCsvData, self.lastBindingsData, self.lastBindingIndex, self.formatTemplates, self.downloadAllBindingPages.get(), self.directoryTrees[self.selectedTree.get()])
            self.downloadThread.daemon = True
            self.downloadThread.start()
            self.master.after(100, self.process_queue)
            self.downloadThreadStarted = True
            self.cancelDownloadButton['state'] = DISABLED
            self.startDownloadButton.config(text="Pause download")
        else:
            self.downloadThread.event.set()
            self.downloadThreadStarted = False
            self.cancelDownloadButton['state'] = DISABLED
            self.startDownloadButton['state'] = DISABLED
            self.startDownloadButton.config(text="Resume download")

    def process_queue(self):

        try:
            msg = self.queue.get(0)
            answers = []

            #Events when download was finished succesfully: "Finished" or if download ended to error: "Finished error"
            if (msg == "Finished"):
                self.downloadThreadStarted = False
                self.startDownloadButton.config(text="Download material")
                self.bar1 = None
                self.lastBindingIndex = -1
                self.removeResumeItems()
                self.resetSelections()
            elif(msg == "Finished error"):
                self.downloadThreadStarted = False
                self.startDownloadButton.config(text="Resume download")
                self.bar1 = None

        except queue.Empty:
            self.master.after(100, self.process_queue)

    def cancelDownload(self):
            self.downloadThreadStarted = False
            self.startDownloadButton.config(text="Download material")
            self.bar1 = None
            self.lastBindingIndex = -1
            self.cancelDownloadButton['state'] = DISABLED
            self.removeResumeItems()

    def resetSelections(self):

        self.selectedOCRFormat.set("")
        self.selectedImageFormat.set("")
        #self.downloadAllBindingPages.set("0")
        #self.saveDirectoryPath.set("")

        #choices = list(self.directoryTrees.keys())
        #self.selectedTree.set(choices[0])
    
    def createLogoFrame(self):

        s = Style()
        s.configure('My.TFrame', background='white')

        self.frame_logosFrame = Frame(self.win, style='My.TFrame')
        self.frame_logosFrame.grid(row = 0, column = 0, sticky = NSEW, padx = 2, pady = (0,0), columnspan=4)
        
        self.frame_logos = Frame(self.frame_logosFrame, style='My.TFrame')
        self.frame_logos.pack()

        s = Style()
        s.configure('My.TLabel', background='white')

        imageKK_path = self.img_resource_path("KK_logo_small2.png")
        imageKK = Image.open(imageKK_path)
        photoKK = ImageTk.PhotoImage(imageKK)

        labelKK = Label(self.frame_logos,image=photoKK, style='My.TLabel')
        labelKK.image = photoKK # this line need to prevent gc
        labelKK.pack(side="left",padx=(30, 30),pady=(10, 10))

        image1_path = self.img_resource_path("sosiaali_fi_small3.png")
        image1 = Image.open(image1_path)
        photo1 = ImageTk.PhotoImage(image1)

        label1 = Label(self.frame_logos,image=photo1, style='My.TLabel')
        label1.image = photo1 # this line need to prevent gc
        label1.pack(side="left", padx=(0, 15),pady=(22, 10))

        image2_path = self.img_resource_path("fi_EU_rgb_small2.png")
        image2 = Image.open(image2_path)
        photo2 = ImageTk.PhotoImage(image2)

        label2 = Label(self.frame_logos,image=photo2, style='My.TLabel')
        label2.image = photo2 # this line need to prevent gc
        label2.pack(side="left", padx=(0, 0),pady=(10, 10))

    def createAineistoFrame(self):

        self.frame_aineisto = Labelframe(self.win, text='Address of the Digi page with the search results', labelanchor=N+S)
        self.frame_aineisto.grid(row = 1, column = 0, sticky = NSEW, padx = 2, pady = 2)

        self.digiResultsUrl = Text(self.frame_aineisto, height=1, width=35)
        self.digiResultsUrl.configure(font=("helvetica", 10))
        self.digiResultsUrl.pack(fill=X)

    def createOCRFormatFrame(self):
        self.frame_formaatti = Labelframe(self.win, text='Text format', labelanchor=N+S)
        self.frame_formaatti.grid(row = 1, column = 1, sticky = NSEW, padx = 2, pady = 2) 

        self.selectedOCRFormat = StringVar()

        self.frame_radioButtons = Frame(self.frame_formaatti)
        R1 = Radiobutton(self.frame_radioButtons, text="ALTO xml", value="alto", var=self.selectedOCRFormat)
        R2 = Radiobutton(self.frame_radioButtons, text="text", value="txt", var=self.selectedOCRFormat)
        R1.pack(side="left")
        R2.pack(side="left")
        self.frame_radioButtons.pack()

    def createImageFormatFrame(self):
        self.frame_ImageFormat = Labelframe(self.win, text='Pictures', labelanchor=N+S)
        self.frame_ImageFormat.grid(row = 1, column = 2, sticky = NSEW, padx = 2, pady = 2) 

        self.selectedImageFormat = StringVar()

        self.frame_imageRadioButtons = Frame(self.frame_ImageFormat)
        R1 = Radiobutton(self.frame_imageRadioButtons, text="jpg pictures", value="jpg", var=self.selectedImageFormat)
        R2 = Radiobutton(self.frame_imageRadioButtons, text="pdf", value="pdf", var=self.selectedImageFormat)
        R1.pack(side="left")
        R2.pack(side="left")
        self.frame_imageRadioButtons.pack()
    
    def createDownloadBindingPagesFrame(self):
        self.frame_BindingPages = Labelframe(self.win, text='Download all pages of the volume', labelanchor=N+S)
        self.frame_BindingPages.grid(row = 1, column = 3, sticky = NSEW, padx = 2, pady = 2) 

        self.downloadAllBindingPages = StringVar()
        pagesCheckButton = Checkbutton(self.frame_BindingPages, text="", var=self.downloadAllBindingPages)
        pagesCheckButton.pack()

    def createSaveDirectoryBrowser(self):
        # Create a Tkinter variable
        self.saveDirectoryPath = StringVar()

        pathname = os.path.dirname(sys.argv[0])
        #pathname = os.path.abspath(os.path.join(pathname, os.pardir))
        self.saveDirectoryPath.set(os.path.abspath(pathname))

        def browse_button():
            # Allow user to select a directory and store it in global var
            filename = filedialog.askdirectory()
            if filename == "":
                filename = os.path.abspath(pathname)

            self.saveDirectoryPath.set(filename)

        self.frame_saveDirectoryFrame = Labelframe(self.win, text='Material storage location', labelanchor=N+S)
        self.frame_saveDirectoryFrame.grid(row = 2, column = 0, sticky = NSEW, padx = 2, pady = 2, columnspan=3)

        self.directoryLabel = Label(self.frame_saveDirectoryFrame,textvariable=self.saveDirectoryPath)
        self.directoryLabel.pack(side="left", expand = False)
        self.browseButton = Button(self.frame_saveDirectoryFrame, text="Choose location", command=browse_button)
        self.browseButton.pack(side="right")

        self.frame_directoryTreeFrame = Labelframe(self.win, text='Directory tree structure', labelanchor=N+S)
        self.frame_directoryTreeFrame.grid(row = 2, column = 3, sticky = NSEW, padx = 2, pady = 2, columnspan=1)

        # Create a Tkinter variable
        self.selectedTree = StringVar()

        choices = list(self.directoryTrees.keys())
        self.selectedTree.set(choices[0]) # set the default option

        self.popupMenu = Combobox(self.frame_directoryTreeFrame, state="readonly", textvariable = self.selectedTree, values = choices)
        self.popupMenu.configure(width=25)
        self.popupMenu.pack(side="right")

    def setDownloadResumeItems(self, lastBindingIndex, lastBindingsData, hitsData, totalPagesData, bindingsCsvData, formatTemplates):
        self.lastBindingIndex = lastBindingIndex
        self.lastBindingsData = lastBindingsData
        self.hitsData = hitsData
        self.totalPagesData = totalPagesData
        self.bindingsCsvData = bindingsCsvData
        self.formatTemplates = formatTemplates

        #enable resume download button and cancel download button, when last binding download has been canceled and resume button can be enabled
        self.startDownloadButton['state'] = NORMAL
        self.cancelDownloadButton['state'] = NORMAL

        with open('resumeItems.pkl', 'wb') as f:
            pickle.dump([self.lastBindingIndex, self.lastBindingsData, self.hitsData, self.totalPagesData, self.bindingsCsvData, self.digiResultsUrl.get("1.0",'end-1c'), self.selectedOCRFormat.get(), self.selectedImageFormat.get(), self.saveDirectoryPath.get(), self.formatTemplates, self.downloadAllBindingPages.get(), self.selectedTree.get()], f)

    def createKeywordsGraph(self, hitsData, totalPagesData, bindingsCsvData, isResumeDownload):
        title = "Pages included in the search"

        if len(hitsData) > 0 and len(totalPagesData) == 0:
            self.hitsDf = pd.DataFrame(hitsData,columns=['year','amount'])
            self.df1 = self.hitsDf
        elif len(totalPagesData) > 0:
            if len(hitsData) == 0:
                self.totalPagesDf = pd.DataFrame({'Pages included in the search': totalPagesData["amount"]}, index=totalPagesData["year"])
            else:
                for i in range(len(totalPagesData["year"])):
                    years = totalPagesData["year"]
                    if not years[i] in hitsData["year"]:
                        hitsData["year"].insert(i, years[i])
                        hitsData["amount"].insert(i, 0)
                self.totalPagesDf = pd.DataFrame({'Pages included in the search': totalPagesData["amount"],'Pages containing the search terms':hitsData["amount"]}, index=totalPagesData["year"])
            self.totalPagesDf.index.name = "Vuosi"
            self.df1 = self.totalPagesDf

            if self.joinExcels.get() == "1" and self.lastBindingIndex == -1:
                self.joinPageCountsCsvDf = self.joinPageCountsCsvDf.add(self.df1, fill_value=0)
                self.df1 = self.joinPageCountsCsvDf 

        self.bindingsCsvDf = pd.DataFrame(bindingsCsvData,columns=['bindingTitle','bindingId','publicationId','date','issue','generalType','publisher','pageNumber','textHighlights','terms','url', 'copyrights', 'references'])
        self.bindingsCsvDf = self.bindingsCsvDf.sort_values(by=['date'])
        self.bindingsCsvDf.index.name = "index"

        #checks that excel join is enabled and that download is not canceled
        if self.joinExcels.get() == "1" and self.lastBindingIndex == -1:
            self.joinBindingsCsvDf = pd.concat([self.joinBindingsCsvDf, self.bindingsCsvDf], ignore_index=True, sort=False)
            self.bindingsCsvDf = self.joinBindingsCsvDf

        if self.frame_graphContent != None:
            self.frame_graphContent.grid_forget()
            self.ax1.clear()

        self.frame_graphContent = Frame(self.win)
        self.frame_graphContent.grid(row = 4, column = 0, sticky = NSEW, padx = 2, pady = 2, columnspan=4)

        totalYears = len(totalPagesData["year"])
        if totalYears < 50:
            widthScale = totalYears / 24
            figSize = (8*widthScale,6)
        else:
            figSize = (4,6)
        self.figure1 = plt.Figure(figsize= figSize, dpi=70)

        self.ax1 = self.figure1.add_subplot(111)
        self.ax1.set_xticks(np.arange(len(totalPagesData["year"])))
        self.df1.plot(kind='bar', legend=True, ax=self.ax1)
        self.bar1 = FigureCanvasTkAgg(self.figure1, self.frame_graphContent)
        self.bar1.get_tk_widget().pack(fill=X)
        
        self.ax1.set_title(title)
        self.ax1.set_xlabel('')
        self.ax1.set_ylabel('')

        if totalYears < 10:
            self.figure1.autofmt_xdate(bottom=0.2, rotation=0, ha="center")
 
        self.frame_saveButtons = Frame(self.frame_graphContent)

        if len(hitsData) > 0 or len(totalPagesData) > 0:
            self.saveHitsButton = Button(self.frame_saveButtons, text="Save the number of search result pages",command= lambda: self.askCsvPath(self.df1, "search_result_pages.csv"))
            self.saveHitsButton.pack(side="left")

        self.saveBindingDataButton = Button(self.frame_saveButtons, text="Save the information on downloaded materials",command= lambda: self.askCsvPath(self.bindingsCsvDf, "downloaded_materials.csv"))
        self.saveBindingDataButton.pack(side="left")

        self.frame_saveButtons.pack()

        self.frame_joinExcels = Frame(self.frame_graphContent)

        joinButton = Checkbutton(self.frame_joinExcels, text="Merge the CSV files of future downloads", var=self.joinExcels)
        joinButton.pack()

        self.frame_joinExcels.pack()

        # on change dropdown value
        def formatChanged(*args):
            if self.joinExcels.get() == "1":
                self.joinBindingsCsvDf = self.bindingsCsvDf
                self.joinPageCountsCsvDf = self.df1

        self.joinExcels.trace('w', formatChanged)

        if not isResumeDownload:
            self.saveCsv(self.bindingsCsvDf, self.saveDirectoryPath.get() + '/' + "downloaded_materials.csv", True)

    def createStatusTextWidget(self):

        self.frame_statusFrame = Labelframe(self.win, text='Download status', labelanchor=N+S)
        self.frame_statusFrame.grid(row = 5, column = 0, sticky = NSEW, padx = 2, pady = 2, columnspan=4)

        self.statusText = Label(self.frame_statusFrame, text="")
        self.statusText.pack(side="left")

    def img_resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

    def askCsvPath(self, df, fileName):
        data = [('csv', '*.csv')]
        
        path = filedialog.asksaveasfile(mode='a', filetypes=data, defaultextension=data,initialfile = fileName)
        if path is None: # asksaveasfile return `None` if dialog closed with "cancel".
            return

        self.saveCsv(df, path.name, False)

    def saveCsv(self,resultDf,csvPath, isAutoSave):
        resultCsv = resultDf.to_csv(header=True, line_terminator='\n')
        try:
            if isAutoSave:
                now = datetime.now() # current date and time
                date_time = now.strftime("%d.%m.%Y_%H.%M.%S")
                csvPath = csvPath.replace(".csv", "_" + date_time + ".csv")

            f=open(csvPath, "w", errors="ignore")    
            f.write(resultCsv)
            f.close()
        except PermissionError:

            now = datetime.now() # current date and time
            date_time = now.strftime("%d.%m.%Y_%H.%M.%S")
            
            csvPath = csvPath.replace(".csv", "_" + date_time + ".csv")
            f=open(csvPath, "w", errors="ignore")    
            f.write(resultCsv)
            f.close()

root = Tk()
app = Application(master=root)
app.mainloop()