import pandas as pd
from tkinter import *
from tkinter import filedialog
from tkinter.ttk import *  
from tkinter import PanedWindow
from PIL import ImageTk,Image, ImageDraw
import os
from tkinter.font import Font
import sys
from cef_browser import CefBrowser
import threading
from datetime import datetime
import math
import ast
import DataFrameCreator
import gettext
from multiprocessing import freeze_support


#number of results to show in hit items list
MAXPAGERRESULTS = 25

class CsvViewer:

    def reDrawPage(self):

        row = self.df.loc[self.df["indexCounter"] == self.currentPageIndex]
        pageTerms = row["termRegions"].item()
        currentjpg = row["jpgPath"].item()

        source_img = Image.open(currentjpg).convert('RGBA')
        overlay = Image.new('RGBA', source_img.size, self.TINT_COLOR+(0,))
        draw = ImageDraw.Draw(overlay)

        try:
            dpi = source_img.info['dpi'][0] # 200
        except KeyError:
            dpi = 300
        

        for term in pageTerms:
            shape = [(dpi * term[0] / 254, dpi * term[1] / 254), (dpi * term[0] / 254 + dpi * term[3] / 254, dpi * term[1] / 254 + dpi * term[2] / 254)]
            draw.rectangle(shape,  width = 5,  fill=self.TINT_COLOR+(self.OPACITY,))
            
        source_img = Image.alpha_composite(source_img, overlay)


        img1 = ImageTk.PhotoImage(image=source_img)
        return img1

    def selectTextWidget(self,widgetIndex):

        if (widgetIndex != self.currentPageIndex):

            self.textWidgetKeys[widgetIndex].configure(highlightthickness=4, highlightbackground="#37d3ff")
            self.textWidgetKeys[self.currentPageIndex].configure(highlightthickness=0)

            self.currentPageIndex = widgetIndex

            img1 = self.reDrawPage()
            img1 = img1._PhotoImage__photo.subsample(self.pageZoomLevel)

            self.itemImageLabel.configure(image=img1)
            self.itemImageLabel.image = img1

            currentRow = self.df.loc[self.df["indexCounter"] == self.currentPageIndex]

            self.commentText.delete("1.0", END)

            if "comment" in currentRow:
                if pd.notnull(currentRow["comment"].item()):
                    self.commentText.insert("1.0", currentRow["comment"].item())

            self.root.update()

        if not self.selectionAfterLinkClick:
            #hides browser frame and shows scrollbars that are needed to scroll image
            self.cefBrowser.browser_frame.pack_forget()
            self.image_vscroll.pack(side="right", fill="y")
            self.image_hscroll.pack(side="bottom", fill="x")
            self.imagecanvas.pack(side="left", fill="both", expand=True)
            #update() call needed to make sure image is every time changed
            self.root.update()
        else:
            self.selectionAfterLinkClick = False

    def mouseClick(self,button):

        if button == 0:
            self.pageZoomLevel += 1

            #sets canvas to zero position, so that when zooming out page is visible when zooming is over
            self.imagecanvas.xview_moveto(0)
            self.imagecanvas.yview_moveto(0)
        elif self.pageZoomLevel > 1:
            self.pageZoomLevel -= 1

        if self.pageZoomLevel > 0:
            img1 = self.reDrawPage()
            img1 = img1._PhotoImage__photo.subsample(self.pageZoomLevel)

            self.itemImageLabel.configure(image=img1)
            self.itemImageLabel.image = img1

    #moves/scrolls canvas that displays page image to coordinates that are given in hitCoords parameter
    def scrollToHit(self,hitCoords, index):

        self.selectTextWidget(index)

        #sets page zoom to 1 so it is mazimized and displays highlighted words correctly and in correct position
        if (self.pageZoomLevel != 1):
            self.pageZoomLevel = 1
            img1 = self.reDrawPage()
            img1 = img1._PhotoImage__photo.subsample(self.pageZoomLevel)

            self.itemImageLabel.configure(image=img1)
            self.itemImageLabel.image = img1
            self.itemImageLabel.pack(side=LEFT,fill=BOTH)


        self.imagecanvas.configure(xscrollincrement=1)
        self.imagecanvas.configure(yscrollincrement=1)

        self.imagecanvas.xview_moveto(0)
        self.imagecanvas.yview_moveto(0)

        self.imagecanvas.xview_scroll(int(hitCoords[0]), "units")
        self.imagecanvas.yview_scroll(int(hitCoords[1]), "units")

        self.imagecanvas.configure(xscrollincrement=0)
        self.imagecanvas.configure(yscrollincrement=0)

        self.root.update()

    def on_mousewheel(self,event,canvas):
        canvas.yview_scroll((int)(-1*(event.delta/120)), "units")


    def set_binds_canvas1(self,event):
        self.hitcanvas_frame.bind_all("<MouseWheel>", lambda event, canvas=self.hitcanvas: self.on_mousewheel(event, canvas))

    def set_unbinds_canvas1(self):
        self.hitcanvas_frame.unbind_all("<MouseWheel>")

    def set_binds_canvas2(self,event):
        self.imagecanvas_frame.bind_all("<MouseWheel>", lambda event, canvas=self.imagecanvas: self.on_mousewheel(event, canvas))

    def MouseWheelHandler(self,event):
        global img1
        global draw_canvas
        global current_image

        def delta(event):
            if event.num == 5 or event.delta < 0:
                return -1 
            return 1 

        self.pageZoomLevel -= delta(event)

        if self.pageZoomLevel > 0:
            img1 = ImageTk.PhotoImage(file=self.jpgs[0])
            img1 = img1._PhotoImage__photo.subsample(self.pageZoomLevel)
            draw_canvas.itemconfigure(current_image, image=img1)

    def onFrameConfigure(self, event, canvas):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def onCanvasConfigure(self, event, canvas, canvas_window):
        canvas_width = event.width
        canvas.itemconfig(canvas_window, width=canvas_width)

    def saveCsv(self,resultDf,csvPath):

        try:
            #saves csv without indexCounter column.
            resultCsv = resultDf.drop(["indexCounter"], axis=1).to_csv(header=True, line_terminator='\n', index=False)

            f=open(csvPath, "w", encoding="utf-8", errors="ignore")    
            f.write(resultCsv)
            f.close()

            self.setStatusText(_("Muutokset tallennettu csv-tiedostoon!"), "green")
            
            return True
        
        except PermissionError:
            self.setStatusText(_("Tallennus csv-tiedostoon epäonnistui, sulje mahdollisesti avattuna oleva csv-tiedosto!"), "red")

            return False

    def removeSelectedHitItem(self):

        #checks that there is result to remove
        if self.numberOfResults > 0:

            dfBackup = self.df

            removeRow = self.df.loc[self.df["indexCounter"] == self.currentPageIndex]

            self.df = self.df[self.df.indexCounter != self.currentPageIndex]

            moveToPrevPage = False
            saveSuccess = self.saveCsv(self.df, self.csvPath.get())

            if saveSuccess:
                self.textWidgetKeys[self.currentPageIndex].pack_forget()
                self.textWidgets.remove(self.textWidgetKeys[self.currentPageIndex])

                if self.filteredTextWidgets:
                    self.filteredTextWidgets.remove(self.textWidgetKeys[self.currentPageIndex])

                removeJpgPath = removeRow["jpgPath"].item()
                removeAltoPath = removeRow["altoPath"].item()

                if os.path.exists(removeJpgPath) and ".jpg" in removeJpgPath:
                    try:
                        os.remove(removeJpgPath)
                        currentDir = os.path.dirname(removeJpgPath)
                            
                        if len(os.listdir(currentDir)) == 0:
                            os.removedirs(currentDir)
                    except PermissionError:
                        self.setStatusText(_("Kuvan poisto ei onnistunut! Tiedosto voi olla käytössä."), "red")

                if os.path.exists(removeAltoPath) and ".xml" in removeAltoPath:
                    try:
                        os.remove(removeAltoPath)
                        currentDir = os.path.dirname(removeAltoPath)
                            
                        if len(os.listdir(currentDir)) == 0:
                            os.removedirs(currentDir)
                    except PermissionError:
                        self.setStatusText(_("Alton poisto ei onnistunut! Tiedosto voi olla käytössä."), "red")

                #if page filtering is used, use amount of filtered text widgets to calculate correct information to pager
                if self.filteredTextWidgets:
                    self.numberOfResults = len(self.filteredTextWidgets)
                    self.pagerPages = math.ceil(self.numberOfResults / MAXPAGERRESULTS)
                else:
                    self.numberOfResults = len(self.df.index)
                    self.pagerPages = math.ceil(len(self.df.index) / MAXPAGERRESULTS)

                #highlights and selects first hit item from "page" after remove: if filtering is used use filteredTextWidgets
                if not self.df.empty:
                    if self.filteredTextWidgets and self.currentPagerPage * MAXPAGERRESULTS < len(self.filteredTextWidgets):
                        self.selectTextWidget(self.filteredTextWidgets[self.currentPagerPage * MAXPAGERRESULTS].indexValue)
                        self.refreshPager(True)
                    elif not self.filteredTextWidgets and self.currentPagerPage * MAXPAGERRESULTS < len(self.df.index):
                        self.selectTextWidget(self.df.iloc[self.currentPagerPage * MAXPAGERRESULTS]["indexCounter"])
                        #not anymore filtered widgets so clear filter text
                        self.filterText.delete(0,END)
                        self.filterText.insert(0,"")
                        self.refreshPager(True)
                    else:
                        # changes page to previous page, because there is no more more items in this page
                        moveToPrevPage = True
                else:
                    self.refreshPager(True)
            else:
                self.df = dfBackup

            # changes page to previous page, because there is no more more items in this page, highlights first hit item: if filtering is used use filteredTextWidgets
            if moveToPrevPage:
                if self.filteredTextWidgets:
                    self.selectTextWidget(self.filteredTextWidgets[(self.currentPagerPage -1) * MAXPAGERRESULTS].indexValue)
                else:
                    self.selectTextWidget(self.df.iloc[(self.currentPagerPage -1) * MAXPAGERRESULTS]["indexCounter"])
                self.changePagerPage(0)

    
    def setStatusText(self, text, color):
        self.statusText.set(text)
        self.statusTextLabel.pack(fill="x")
        self.statusTextLabel.configure(foreground=color)

        if self.statusTextId is not None:
            self.statusTextLabel.after_cancel(self.statusTextId)

        # hide statusText after 5 seconds
        self.statusTextId = self.statusTextLabel.after(5000, lambda:self.statusText.set(""))

    def saveComment(self):
        if not self.df.empty:
            currentIndex = self.df.index[self.df['indexCounter']==self.currentPageIndex].tolist()
            self.df.at[currentIndex[0], "comment"] = self.commentText.get("1.0","end-1c")
            self.saveCsv(self.df, self.csvPath.get())

    def createCommentFrame(self):

        self.frame_comment = LabelFrame(self.frameone, text=_('Valittuun sivuun liittyvä kommentti'))

        self.commentText = Text(self.frame_comment, height=5, width=35)
        self.commentText.configure(font=("helvetica", 10))
        self.commentText.pack(fill="x")

        #saves comment automatically when typing the comment has ended
        def commentAutoSave(event):
            # cancel the old comment autosave
            if self.commentSaveId is not None:
                self.commentText.after_cancel(self.commentSaveId)

            # create a new  comment autosave
            self.commentSaveId = self.commentText.after(1000, self.saveComment)

        self.commentSaveId = None
        self.commentText.bind('<Key>', commentAutoSave)

        #Forces focus to comment text widget when it is clicked. Sometimes cefbrowser may take focus and this is needed to enable focus to comment text.
        def commentClick(event):
            self.commentText.focus_force()

        self.commentText.bind('<Button-1>', commentClick)

        # Create a Tkinter variable
        self.statusText = StringVar()

        self.statusTextLabel = Label(self.frame_comment, textvariable=self.statusText, font='Helvetica 10 bold')
        self.statusTextLabel.pack(fill="x")
        #id is used in setStatusText function to cancel function call that removes status text, if needed 
        self.statusTextId = None

        self.saveCommentButton = Button(self.frame_comment, text="Tallenna",command= self.saveComment)
        self.frame_comment.pack(side="bottom", fill="x", expand=False)

    def filterPages(self, filterRegex):

        #remove earlier filter highlights from hit texts and hide filteredTextWidgets if there are earlier filters
        if self.filteredTextWidgets:
            for textWidget in self.filteredTextWidgets:
                textWidget.tag_remove("highlightFilter", "1.0", "end")
                textWidget.pack_forget()

        #if filter is empty, remove filter and show normal pages in pager
        if not filterRegex:
            
            self.filteredTextWidgets = []
            self.numberOfResults = len(self.df.index)
            self.pagerPages = math.ceil(len(self.df.index) / MAXPAGERRESULTS)
            self.currentPagerPage = 0
            if self.numberOfResults > 0:
                self.currentPageText.set(str(self.currentPagerPage + 1) + "/" + str(self.pagerPages))
            else:
                self.currentPageText.set("")

            self.totalResultsText.set(_("Tulosten yhteismäärä: ") + str(self.numberOfResults))

            endIndex = (self.currentPagerPage * MAXPAGERRESULTS) + MAXPAGERRESULTS
                    
            if endIndex > self.numberOfResults:
                endIndex = self.numberOfResults

            for x in range(self.currentPagerPage * MAXPAGERRESULTS, endIndex):
                self.textWidgets[x].pack(fill="x", expand=True)
                
                if (x % 2) == 0:
                    self.textWidgets[x]["bg"] = "#D9CB9E"
                else:
                    self.textWidgets[x]["bg"] = "#fff"

        #filter is given, so use it to filter results
        else:
            self.filteredTextWidgets = []
            visibleTextWidgets = 0
            regexFailed = False

            for textWidget in self.textWidgets:
                try:
                    #(?i) turns on case-insensitive mode, (?-i) turns it off. (?-i:Martti Pitkänen)
                    results = [x.group() for x in re.finditer(filterRegex, textWidget.get("1.0",END),flags=re.IGNORECASE)]
                except Exception:
                    regexFailed = True
                    break
                if results:
                    prevEndPosition = "1.0"
                    for result in results:
                        startPosition = textWidget.search(result,prevEndPosition, END)
                        prevEndPosition = '{0}+{1}c'.format(startPosition, len(result))
                        textWidget.tag_add("highlightFilter", startPosition, prevEndPosition)
                        textWidget.tag_config("highlightFilter", background="spring green")

                    if visibleTextWidgets < MAXPAGERRESULTS:
                        if (visibleTextWidgets % 2) == 0:
                            textWidget["bg"] = "#D9CB9E"
                        else:
                            textWidget["bg"] = "#fff"

                        #hide all filtered first, because there can be these widgets already visible and widgets order can be wrong, if they are made visible here.
                        textWidget.pack_forget()
                        visibleTextWidgets +=1
                    else:
                        textWidget.pack_forget()
                    
                    
                    self.filteredTextWidgets.append(textWidget)
                else:
                    textWidget.pack_forget()

            #show all filtered widgets
            for i in range(visibleTextWidgets):
                self.filteredTextWidgets[i].pack(fill="x", expand=True)

            #if there are now filtered widgets move hitcanvas top and call root.update so that filtered widgets come visible every time
            if self.filteredTextWidgets:
                self.hitcanvas.yview_moveto(0)
                self.root.update()
            
            #if filtering was successful, update pager information so it is correct
            if self.filteredTextWidgets:
                self.numberOfResults = len(self.filteredTextWidgets)
                self.pagerPages = math.ceil(self.numberOfResults / MAXPAGERRESULTS)
                self.currentPagerPage = 0
                self.currentPageText.set(str(self.currentPagerPage + 1) + "/" + str(self.pagerPages))
                self.totalResultsText.set(_("Suodatettujen tulosten yhteismäärä: ") + str(self.numberOfResults))
            else:
                if regexFailed:
                    self.setStatusText(_("Annettu säännöllinen lauseke ei ollut toimiva."), "red")
                else: 
                    self.setStatusText(_("Suodatus ei tuottanut tuloksia."), "red")
                    self.currentPageText.set("")
                    self.totalResultsText.set(_("Suodatettujen tulosten yhteismäärä: 0"))

    def refreshPager(self, isAfterItemRemove):
        endIndex = (self.currentPagerPage * MAXPAGERRESULTS) + MAXPAGERRESULTS
        if endIndex > self.numberOfResults:
            endIndex = self.numberOfResults

        for x in range(self.currentPagerPage * MAXPAGERRESULTS, endIndex):
            if self.filteredTextWidgets:
                currentWidget = self.filteredTextWidgets[x]
            else:
                currentWidget = self.textWidgets[x]
                        
            currentWidget.pack(fill="x", expand=True)

            if (x % 2) == 0:
                currentWidget["bg"] = "#D9CB9E"
            else:
                currentWidget["bg"] = "#fff"

        #update currentPageText only when there are results
        if self.numberOfResults > 0:
            self.currentPageText.set(str(self.currentPagerPage + 1) + "/" + str(self.pagerPages))
        else:
            self.currentPageText.set("")

        if self.filteredTextWidgets:
            self.totalResultsText.set(_("Suodatettujen tulosten yhteismäärä: ") + str(self.numberOfResults))
        else:
            self.totalResultsText.set(_("Tulosten yhteismäärä: ") + str(self.numberOfResults))
        #moves hit canvas to top when page changes, does not move to top when textWidget item has been removed and refreshPager has been called
        if not isAfterItemRemove:
            self.hitcanvas.yview_moveto(0)
        self.root.update()

    def changePagerPage(self, direction):

        if direction == 0:
            if self.currentPagerPage > 0:

                endIndex = (self.currentPagerPage * MAXPAGERRESULTS) + MAXPAGERRESULTS
                
                if endIndex > self.numberOfResults:
                    endIndex = self.numberOfResults

                for x in range(self.currentPagerPage * MAXPAGERRESULTS, endIndex):
                    if self.filteredTextWidgets:
                        self.filteredTextWidgets[x].pack_forget()
                    else:
                        self.textWidgets[x].pack_forget()
                
                self.currentPagerPage -=1
                self.refreshPager(False)

        elif direction == 1:
            if self.currentPagerPage + 1 < self.pagerPages:
                for x in range(self.currentPagerPage * MAXPAGERRESULTS, (self.currentPagerPage * MAXPAGERRESULTS) + MAXPAGERRESULTS):
                    if self.filteredTextWidgets:
                        self.filteredTextWidgets[x].pack_forget()
                    else:
                        self.textWidgets[x].pack_forget()
                
                self.currentPagerPage +=1
                self.refreshPager(False)

    def createPagerFrame(self):

        self.pagerPages = math.ceil(len(self.df.index) / MAXPAGERRESULTS)
        self.currentPagerPage = 0

        self.frame_pager = Frame(self.frameone)#, labelanchor=N+S)

        self.prevPageButton = Button(self.frame_pager, text=_("Edellinen"),command= lambda:self.changePagerPage(0))
        self.prevPageButton.pack(side="left", fill="x", expand=True)

        self.currentPageText = StringVar()
        
        if self.numberOfResults > 0:
            self.currentPageText.set(str(self.currentPagerPage + 1) + "/" + str(self.pagerPages))

        self.currentPageLabel = Label(self.frame_pager, textvariable=self.currentPageText, font='Helvetica 18 bold')
        self.currentPageLabel.configure(anchor="center")
        self.currentPageLabel.pack(side="left", fill="x", expand=True)

        self.nextPageButton = Button(self.frame_pager, text=_("Seuraava"), command= lambda:self.changePagerPage(1))
        self.nextPageButton.pack(side="left", fill="x", expand=True)

        self.frame_pager.pack(side="top", fill="x", expand=False)

        self.totalResultsText = StringVar()
        self.totalResultsText.set(_("Tulosten yhteismäärä: ") + str(self.numberOfResults))

        self.frame_totalResults = Frame(self.frameone)
        self.totalResultsLabel = Label(self.frame_totalResults, textvariable=self.totalResultsText, font='Helvetica 10 bold')
        self.totalResultsLabel.configure(anchor="center")
        self.totalResultsLabel.pack(fill="x")
        self.frame_totalResults.pack(side="top", fill="x", expand=False)

    def createFilterFrame(self):

        self.pagerPages = math.ceil(len(self.df.index) / MAXPAGERRESULTS)
        self.currentPagerPage = 0

        self.frame_filter = LabelFrame(self.frameone, text=_('Osumaympäristöjen suodatus'))#, labelanchor=N+S)
        
        self.filterText = Entry(self.frame_filter, width=50)
        self.filterText.pack(side="left", fill="x", expand=True)

        #Forces focus to filter text widget when it is clicked. Sometimes cefbrowser may take focus and this is needed to enable focus to filter text.
        def filterClick(event):
            self.filterText.focus_force()

        self.filterText.bind('<Button-1>', filterClick)

        #call filterPages function when enter key is pressed in filterText
        self.filterText.bind('<Return>', lambda event: self.filterPages(self.filterText.get()))

        self.frame_filter.pack(side="top", fill="x", expand=False)

    def createDownloadDirFrame(self, currentDownloadDirectory=os.path.abspath(os.path.join(os.path.abspath(""), os.pardir)), currentCsvPath=os.path.abspath(os.path.join(os.path.abspath(""), os.pardir))):

        # Create a Tkinter variable
        self.downloadDirectoryPath = StringVar()
        self.downloadDirectoryPath.set(currentDownloadDirectory)

        # Create a Tkinter variable
        self.csvPath = StringVar()
        self.csvPath.set(currentCsvPath)

        self.downloadDirFrame = Frame(self.root)

        self.frame_downloaddir = Labelframe(self.downloadDirFrame, text=_('Ladatun aineiston hakemisto'), labelanchor=N+S)
        self.frame_downloaddir.pack(fill="x")
        self.frame_downloaddir.columnconfigure(0, weight=3)
        self.frame_downloaddir.columnconfigure(1, weight=1)

        self.directoryLabel = Label(self.frame_downloaddir,textvariable=self.downloadDirectoryPath)
        self.directoryLabel.grid(row = 0, column = 0, sticky = W, padx = 2, pady = 2)

        self.frame_downloadcsv = Labelframe(self.downloadDirFrame, text=_('csv-tiedosto'), labelanchor=N+S)
        self.frame_downloadcsv.pack(fill="x")
        self.frame_downloadcsv.columnconfigure(0, weight=3)
        self.frame_downloadcsv.columnconfigure(1, weight=1)

        self.csvLabel = Label(self.frame_downloadcsv,textvariable=self.csvPath)
        self.csvLabel.grid(row = 1, column = 0, sticky = W, padx = 2, pady = 2)

        def browse_directory(storeVariable):
            # Allow user to select a directory and store it in global var
            dirPath = filedialog.askdirectory()
            if dirPath == "":
                dirPath = os.path.abspath(os.path.join(os.path.abspath(""), os.pardir))
            #tries to find last modified .csv file from given folder, and sets it to current csv Path if it is found
            else:
                dirFiles = [s for s in os.listdir(dirPath) if os.path.isfile(os.path.join(dirPath, s))]
                dirFiles.sort(key=lambda s: os.path.getmtime(os.path.join(dirPath, s)), reverse = True)

                firstCsv = next(filter(lambda file: file.endswith('.csv'), dirFiles), None)

                if firstCsv:
                    self.csvPath.set(os.path.join(dirPath, firstCsv))
                    self.okButton["state"] = "normal"
                    self.loadStatusLabel.pack_forget()

            storeVariable.set(dirPath)

        def browse_csvFile(storeVariable):
            # Allow user to select a csv file
            filename = filedialog.askopenfilename(initialdir=os.path.abspath(""), title="Select file",filetypes=(("csv", "*.csv"),))

            if ".csv" in filename:
                storeVariable.set(filename)
                self.okButton["state"] = "normal"
                self.loadStatusLabel.pack_forget()
            else:
                self.currentLoadStatus.set(_("Valitse csv-tiedosto!"))
                self.loadStatusLabel.pack()

        def startContentLoad():
            self.okButton.pack_forget()
            self.loadStatusLabel.configure(foreground="black")
            self.currentLoadStatus.set(_("Aloitetaan käsittelyä"))
            self.loadStatusLabel.pack()
            self.endThreadEvent = threading.Event()
            self.th = threading.Thread(target=self.loadContent, args=(self.downloadDirectoryPath.get(), self.csvPath.get()), daemon=True)
            self.th.setDaemon(True)
            self.th.start()

        self.browseButton = Button(self.frame_downloaddir, text=_("Valitse sijainti"), command= lambda: browse_directory(self.downloadDirectoryPath))
        self.browseButton.grid(row = 0, column = 1, sticky = E, padx = 2, pady = 2)

        self.browseButton2 = Button(self.frame_downloadcsv, text=_("Valitse csv"), command= lambda: browse_csvFile(self.csvPath))
        self.browseButton2.grid(row = 1, column = 1, sticky = E, padx = 2, pady = 2)

        self.okButton = Button(self.downloadDirFrame, text="OK", command=startContentLoad)
        self.okButton.pack(side="bottom", fill="x")
        self.okButton["state"] = "disabled"

        self.currentLoadStatus = StringVar()
        self.currentLoadStatus.set("")
        self.loadStatusLabel = Label(self.downloadDirFrame, textvariable=self.currentLoadStatus)
        
        self.loadStatusLabel.bind("<<loadProgressEvent>>", self.loadProgressHandler)

        self.downloadDirFrame.pack()

        # if csv path is given in args start handling these files automatically and hide browse buttons
        if ".csv" in currentCsvPath:
            startContentLoad()
            self.browseButton.grid_forget()
            self.browseButton2.grid_forget()


    def loadProgressHandler(self, event):
        
        #loading page info to dataframe is complete when state is 1 so start main ui creation
        if event.state == 1:
            #create ui in main thread. ui creation in separate thread may cause problems when using tkinter
            self.createUI()
            #saves csv file with possible new changes
            self.saveCsv(self.df, self.csvPath.get())
        #update dataframe creation progress
        elif event.state == 0:
            self.loadCounter += 1
            self.currentLoadStatus.set(_("Käsitellään sivua: ") + str(self.loadCounter) + "/" + str(len(self.df.index)))
        elif event.state == -1:
            self.loadStatusLabel.configure(foreground="red")
            self.currentLoadStatus.set(_("Tarvittavia tietoja aineistojen tarkasteluun ei löytynyt!"))
            #show okButton, so it is possible to try again
            self.okButton.pack(side="bottom", fill="x")


    def createFrames(self):

        self.panedWindow = PanedWindow(orient=HORIZONTAL, sashwidth=15)

        self.frameone = Frame(self.root)
        self.hitframe = Frame(self.frameone)

        self.hitcanvas = Canvas(self.hitframe, highlightthickness=0)
        self.hitcanvas_frame = Frame(self.hitcanvas)
        self.hit_vscroll = Scrollbar(self.hitframe, orient="vertical", command = self.hitcanvas.yview)
        self.hitcanvas['yscrollcommand'] = self.hit_vscroll.set
        
        self.hit_vscroll.pack(side="right", fill="y")

        self.removeButton = Button(self.hitframe, text=_("Poista valittu sivu"), command=self.removeSelectedHitItem)
        self.removeButton.pack(side="bottom", fill="x")

        self.hitcanvas.pack(fill="both", expand=True)

        #ohje: https://stackoverflow.com/questions/66292221/adding-a-horizontal-scrollbar-in-tkinter-with-the-help-of-canvas

        self.canvas_window = self.hitcanvas.create_window((0,0), window=self.hitcanvas_frame, anchor="nw", tags="self.hitcanvas_frame")

        self.hitcanvas_frame.bind("<Configure>", lambda event, canvas=self.hitcanvas:self.onFrameConfigure(event, canvas))
        self.hitcanvas.bind("<Configure>", lambda event, canvas=self.hitcanvas:self.onCanvasConfigure(event, canvas,self.canvas_window))

        self.createFilterFrame()
        self.createPagerFrame()
        self.hitframe.pack(side = TOP, expand = True, fill = BOTH)
        self.createCommentFrame()

        self.frametwo = Frame(self.root)

        self.imagecanvas = Canvas(self.frametwo)
        self.imagecanvas_frame = Frame(self.imagecanvas)
        self.image_vscroll = Scrollbar(self.frametwo, orient="vertical", command = self.imagecanvas.yview)
        self.imagecanvas['yscrollcommand'] = self.image_vscroll.set
        self.image_hscroll = Scrollbar(self.frametwo, orient="horizontal", command = self.imagecanvas.xview)
        self.imagecanvas['xscrollcommand'] = self.image_hscroll.set

        self.image_vscroll.pack(side="right", fill="y")
        self.image_hscroll.pack(side="bottom", fill="x")
        self.imagecanvas.pack(side="left", fill="both", expand=True)

        self.imagecanvas.create_window((0, 0), window=self.imagecanvas_frame, anchor='nw')

        self.imagecanvas_window = self.imagecanvas.create_window((0,0), window=self.imagecanvas_frame, anchor="nw", tags="self.imagecanvas_frame")

        self.imagecanvas_frame.bind("<Configure>", lambda event, canvas=self.imagecanvas:self.onFrameConfigure(event, canvas))

        self.cefBrowser =  CefBrowser(self.frametwo, self.closeCefBrowser, self.showBrowserConnectionError)
        self.cefBrowser.browser_frame.browserStarted = False

    def __init__(self):

        #get localization, set language to en = english, fi = finnish or sv = swedish
        el = gettext.translation('base_csv_viewer', localedir='translations', languages=['en'])
        el.install()
        _ = el.gettext
        #_ = gettext.gettext

        #creates tkinter window
        self.root = Tk()
        self.root.title(_("Tarkastelutyökalu"))

        args = sys.argv[1:]

        #sets and creates download directory selection frame if download dir path and csv path have been given in args. Also handling files from these paths is started automatically.
        if args:
            self.createDownloadDirFrame(args[0], args[1])
        else:
            self.createDownloadDirFrame()

        def on_closing():
            #checks if CsvViewer has cefBrowser attribute/cefBrowser has been started so it can be shutdown. closeCefBrowser is called from cef_browser when shutdown is possible
            if hasattr(self,'cefBrowser'):
                if self.cefBrowser.browser_frame.browserStarted:
                    self.cefBrowser.close()
                else:
                    sys.exit(0)
            else:
                sys.exit(0)

        self.root.protocol("WM_DELETE_WINDOW", on_closing)

        self.root.mainloop()

    #this function is called from cef_browser.py, when shutdown is possible
    def closeCefBrowser(self):
        self.cefBrowser.shutdown()
        sys.exit()

    def showBrowserConnectionError(self):
        self.setStatusText(_("Ei yhteyttä palvelimeen!"), "red")

    def createUI(self):
        self.createFrames()

        self.loadCounter = 0
        loadFailed = False

        for index, row in self.df.iterrows():

            self.loadCounter += 1

            #update hitarea ui creation progress, self.root.update() needed to update the text
            self.currentLoadStatus.set(_("Luodaan käyttöliittymään osumaympäristöä sivulle: ") + str(self.loadCounter) + "/" + str(len(self.df.index)))
            self.root.update()
            creationState = self.createHitItems(index,row)

            if creationState == -1:
                self.loadStatusLabel.configure(foreground="red")
                self.currentLoadStatus.set(_("Csv-tiedostossa määriteltyä kuvatiedostoa ei löytynyt!"))
                self.root.update()
                loadFailed =True
                break

        #proceed only if all images were found
        if not loadFailed:

            #hide download directory frame
            self.downloadDirFrame.pack_forget()

            self.frametwo.pack(side = LEFT, expand = True, fill = BOTH)
            self.frameone.pack(side = RIGHT, expand = True, fill = BOTH)
            self.panedWindow.add(self.frametwo, stretch='always', sticky=NSEW)
            self.panedWindow.add(self.frameone, stretch='always', sticky=NSEW)
            self.panedWindow.pack(fill=BOTH, expand=True)
            self.root.state('zoomed')

            if hasattr(self,'itemImageLabel'):
                self.itemImageLabel.bind("<Button-1>", lambda event, button=1: self.mouseClick(button))
                self.itemImageLabel.bind("<Button-3>",lambda event, button=0: self.mouseClick(button))

            self.hitcanvas_frame.bind("<Enter>", self.set_binds_canvas1)
            self.imagecanvas_frame.bind("<Enter>", self.set_binds_canvas2)
        else:
            #show okButton, so it is possible to try again
            self.okButton.pack(side="bottom", fill="x")

    def loadContent(self, downloadDir, csvFile):

        #Defines color for word highlight that are shown in page
        self.TINT_COLOR = (255,127,80)  # orange
        TRANSPARENCY = .55  # Degree of transparency, 0-100%
        self.OPACITY = int(255 * TRANSPARENCY)

        self.jpgs = []
        self.altos = []
        self.termRegions = {}

        self.textWidgets = []
        self.filteredTextWidgets = []
        self.textWidgetKeys = {}
        self.currentPageIndex = 0
        self.pageZoomLevel = 1

        self.downloadDir = downloadDir

        #comment column datatype specified as string, because if user would place numbers to comment, it could cause datatype to be automatically float
        self.df = pd.read_csv(csvFile, encoding = "utf-8", dtype={'comment': 'str'}, keep_default_na=False)#"ladatut_aineistot_15.03.2022_09.59.03.csv", encoding = "utf-8")#"ISO-8859-1") #index_col=[0]
        self.numberOfResults = len(self.df.index)

        neededColumns = ["termRegions", "hitCoords", "altoPath", "jpgPath"]
        csvColumns = list(self.df.columns)

        #if needed columns for dataframe has been already generated when the tools was earlier used and columns exists in csv use columns from csv
        if all(x in csvColumns for x in neededColumns):
            self.df['indexCounter'] = self.df.reset_index().index
            self.df["termRegions"] = self.df['termRegions'].apply(lambda x: ast.literal_eval(x))
            self.df["hitCoords"] = self.df['hitCoords'].apply(lambda x: ast.literal_eval(x))
            
            #generates event at the end to mark that loading has ended and main ui can be created
            self.loadStatusLabel.event_generate("<<loadProgressEvent>>", state=1, when="mark")

        #generate dataframe, because there was not needed columns 
        else:
            for subdir, dirs, files in os.walk(downloadDir):
                for file in files:
                    if ".jpg" in file:
                        self.jpgs.append(os.path.join(subdir, file))
                        self.currentLoadStatus.set(_("Etsitään ladattuja tiedostoja: ") + str(len(self.jpgs)))

                    if ".xml" in file:
                        self.altos.append(os.path.join(subdir, file))

            self.df["termRegions"] = ""
            self.df["termRegions"] = self.df["termRegions"].astype('object')
            self.df["hitCoords"] = ""
            self.df["hitCoords"] = self.df["hitCoords"].astype('object')
            self.df["comment"] = ""
            
            self.df['indexCounter'] = self.df.reset_index().index

            self.futures = []
            self.loadCounter = 0

            def dataFrameCallback(state):
                self.loadStatusLabel.event_generate("<<loadProgressEvent>>",  state=state, when="mark")

            dataframeCreator = DataFrameCreator.DataFrameCreator("t")
            dataframeCreator.createDataFrameProcesses(self.df, self.loadStatusLabel, self.altos, self.jpgs, dataFrameCallback)
    
    def createHitItems(self, index, row): 

        pageTerms = row["termRegions"]
        currentjpg = row["jpgPath"]
        #Needed to check if url has been clicked when selecting hit item and so it is know if browser window has to be kept visible
        self.selectionAfterLinkClick = False

        try:
            source_img = Image.open(currentjpg).convert('RGBA')
        except OSError as e:
            return -1

        try:
            dpi = source_img.info['dpi'][0]
        except KeyError:
            dpi = 300

        text = Text(self.hitcanvas_frame, width=100, wrap=WORD)

        if (index % 2) == 0:
            text["bg"] = "#D9CB9E"

        if index < MAXPAGERRESULTS:
            text.pack(fill="x", expand=True)

        #if is first item in dataframe show it's image in user interface
        if index == 0:

            overlay = Image.new('RGBA', source_img.size, self.TINT_COLOR+(0,))
            draw = ImageDraw.Draw(overlay)

            for term in pageTerms:
                shape = [(dpi * term[0] / 254, dpi * term[1] / 254), (dpi * term[0] / 254 + dpi * term[3] / 254, dpi * term[1] / 254 + dpi * term[2] / 254)]
                draw.rectangle(shape,  width = 5,  fill=self.TINT_COLOR+(self.OPACITY,))
            
            source_img = Image.alpha_composite(source_img, overlay)

            img1 = ImageTk.PhotoImage(image=source_img)
            self.itemImageLabel = Label(self.imagecanvas_frame, image=img1)
            self.itemImageLabel.image = img1
            self.itemImageLabel.pack(side=LEFT,fill=BOTH)

            #highlight first item
            text.configure(highlightthickness=4, highlightbackground="#37d3ff")

            #set first item comment
            currentRow = self.df.loc[self.df["indexCounter"] == 0]

            if "comment" in currentRow:
                if pd.notnull(currentRow["comment"].item()):
                    self.commentText.insert("1.0", currentRow["comment"].item())
            
        #sets textwidgets height to match the height of the text that is displayed inside the textwidget.
        def updateTextHeight(textWidget):
                height = textWidget.count("1.0", "end", "displaylines")
                textWidget.configure(height=height)

        self.textWidgets.append(text)
        self.textWidgets[index].bind('<Map>', lambda event, textWidget=self.textWidgets[index]: updateTextHeight(textWidget))
        self.textWidgets[index].bind('<Configure>', lambda event, textWidget=self.textWidgets[index]: updateTextHeight(textWidget))
        self.textWidgets[index].bind("<ButtonRelease-1>", lambda event, index=row["indexCounter"]: self.selectTextWidget(index))
        
        #creates title for current page and shows it with bolded font in textwidget.
        bindingDate = datetime.strptime(str(row["date"]), '%Y-%m-%d')
        date = bindingDate.strftime("%d.%m.%Y")
        issueNumber = _(" numero ") + str(row["issue"]) if row["issue"] else "" #not math.isnan(row["issue"]) else ""
        itemTitle = str(row["bindingTitle"]) + " " + date + issueNumber + _(" sivu ") + str(row["pageNumber"]) + "\n\n"
        text.insert('1.0', itemTitle)
        text.tag_add("highlightTitle", "1.0", text.search("\n","1.0", END))

        # Creates a bold font
        bold_font = Font(family="Helvetica", size=10, weight="bold")
        text.tag_configure("BOLD", font=bold_font)
        text.tag_add("BOLD", "1.0", text.search("\n","1.0", END))

        def openUrl(url, index):
            self.selectionAfterLinkClick = True

            #sets url to browser, sets it's frame visible and hides scrollbars that are needed to scroll image
            
            self.cefBrowser.goToUrl(url)
            self.cefBrowser.browser_frame.browserStarted = True

            self.imagecanvas.pack_forget()
            self.image_hscroll.pack_forget()
            self.image_vscroll.pack_forget()

            self.cefBrowser.browser_frame.pack(side="left", fill="both", expand=True)
            self.root.update()
            self.filterText.focus_force()
            self.commentText.focus_force()

        #add url to title text. Clicked url is opened in web browser
        self.textWidgets[index].tag_bind("BOLD", "<Button-1>", lambda event, url=row["url"], index=row["indexCounter"]: openUrl(url,index))

        text.tag_config("highlightTitle", background="yellow", foreground="black")

        #splits textHighlights by '###' chars if textHighlights are not empty
        itemHits = str(row["textHighlights"]).split("###") if row["textHighlights"] else []

        startPositions = []
        endPositions = []
        hitPositions = []

        hitIndex = 0

        for item in itemHits:
            cur = 1.0
            cur2 = 1.0
            text.insert(END, item + "...\n\n")
            while True:
                cur = text.search("<em>",cur, END)
                if not cur:
                    break
                else:
                    startPositions.append(cur)

                    matchEnd = '{0}+{1}c'.format(cur, 4)
                    text.delete(cur, matchEnd)
                    
                    cur2 = text.search("</em>",cur2, END)
                    endPositions.append(cur2)

                    matchEnd2 = '{0}+{1}c'.format(cur2, 5)
                    text.delete(cur2, matchEnd2)

                    cur = text.index(matchEnd)
                    cur2 = text.index(matchEnd2)

                    hitPositions.append(hitIndex)

                if cur == "" or cur2 == "":
                    break
            hitIndex += 1

        endIndex = 0

        for hitPosition in startPositions:
            text.tag_add("highlightHit" + str(endIndex), str(hitPosition),  str(endPositions[endIndex]))
            text.tag_config("highlightHit" + str(endIndex), background="orange", foreground="black")

            hitCoords = self.df.at[index, "hitCoords"]
            
            if hitCoords:

                hitX = (dpi * hitCoords[hitPositions[endIndex]][0] / 254)
                hitY = (dpi * hitCoords[hitPositions[endIndex]][1] / 254)

                hitCoords = [hitX, hitY]

                self.textWidgets[index].tag_bind("highlightHit" + str(endIndex), "<Button-1>", lambda event, hitCoords=hitCoords, index=row["indexCounter"]: self.scrollToHit(hitCoords, index))

            endIndex +=1

        self.textWidgets[index].indexValue = row["indexCounter"]
        self.textWidgetKeys[row["indexCounter"]] = self.textWidgets[index]

        text['state'] = 'disabled'

        return 1

if __name__ == '__main__':
    freeze_support()
    viewer = CsvViewer()