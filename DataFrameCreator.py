import os
import threading
import concurrent.futures
import threading
from xml.dom.minidom import parse
import html
from concurrent.futures.process import BrokenProcessPool

class DataFrameCreator:

    def __init__(self, name):
        self.name = name

    def parseTextsFromXml(self, path):
        xmlWords = {}
        wordCounter = 0
 
        prevSubsContent = ""
        currentHighlightCoords = []
    
        dom = parse(path)
        
        for element in dom.getElementsByTagName('String'):

            currentTexts = []

            currentSubsContent = element.getAttribute('SUBS_CONTENT').split(" ")
                        
            if currentSubsContent != prevSubsContent and currentSubsContent[0]:
                currentTexts = currentSubsContent
                prevSubsContent = currentSubsContent
                currentHighlightCoords = []
                currentHighlightCoords.append([float(element.getAttribute('HPOS')), float(element.getAttribute('VPOS')), float(element.getAttribute('HEIGHT')), float(element.getAttribute('WIDTH'))])
            
            elif currentSubsContent == prevSubsContent and currentSubsContent[0]:
                currentHighlightCoords.append([float(element.getAttribute('HPOS')), float(element.getAttribute('VPOS')), float(element.getAttribute('HEIGHT')), float(element.getAttribute('WIDTH'))])
                xmlWords[wordCounter-1][3] = currentHighlightCoords

            elif not currentSubsContent[0]:
                currentTexts = element.getAttribute('CONTENT').split(" ")
                prevSubsContent = ""
                currentHighlightCoords = []
                currentHighlightCoords.append([float(element.getAttribute('HPOS')), float(element.getAttribute('VPOS')), float(element.getAttribute('HEIGHT')), float(element.getAttribute('WIDTH'))])

            for currentText in currentTexts:
                #element.parentNode.parentNode gets words TextBlock from xml and reads it x and y coordinates, does not add empty words
                if currentText:
                    xmlWords[wordCounter]=[currentText, float(element.parentNode.getAttribute('HPOS')), float(element.parentNode.getAttribute('VPOS')),currentHighlightCoords]
                    wordCounter +=1
        
        return xmlWords

    def findHitCoords(self, xmlPath, hitTexts, terms):

        hitCoords = []
        highlightCoords = []
        currentHitIndex = 0

        #splits terms by space if there are terms that contain multiple words, example "Mikkelin kaupunki"
        terms = [word for line in terms for word in line.split()]
        
        currentXmlWords = self.parseTextsFromXml(xmlPath)

        for hit in hitTexts:
            hitWords = hit.split(" ")

            #remove empty chars from list of strings
            hitWords = [i for i in hitWords if i]

            xCoordinate = [0]
            yCoordinate = [0]

            hitIndex = 0

            for xmlWord in currentXmlWords:

                if hitWords[hitIndex] in currentXmlWords[xmlWord][0]:

                    if any(currentWord in hitWords[hitIndex] for currentWord in terms):

                        if xCoordinate[0] == 0 and yCoordinate[0] == 0:
                            xCoordinate[0] = currentXmlWords[xmlWord][1]
                            yCoordinate[0] = currentXmlWords[xmlWord][2]

                        for highlightCoord in currentXmlWords[xmlWord][3]:
                            highlightCoords.append(highlightCoord)

                    hitIndex += 1

                    if hitIndex == len(hitWords):
                        break
                # handles situation where start of hit area is found, when iterating through xml words
                elif hitWords[0] in currentXmlWords[xmlWord][0]:
                    if any(currentWord in hitWords[0] for currentWord in terms):
                        if xCoordinate[0] == 0 and yCoordinate[0] == 0:
                            xCoordinate[0] = currentXmlWords[xmlWord][1]
                            yCoordinate[0] = currentXmlWords[xmlWord][2]

                        for highlightCoord in currentXmlWords[xmlWord][3]:
                            highlightCoords.append(highlightCoord)

                    hitIndex = 1

                    if hitIndex == len(hitWords):
                        break

                else:
                    hitIndex = 0
                    xCoordinate = [0]
                    yCoordinate = [0]

            if xCoordinate[0] != 0 or yCoordinate[0] != 0:
                hitCoords.append([xCoordinate[0], yCoordinate[0]])
            else:
                #with open("missing_coords.txt", "a") as missing:
                #    missing.write(xmlPath + " " + str(hitTexts) + " " + str(terms) + "\n")
                hitCoords.append([0, 0])
            
            currentHitIndex +=1
            
        return [hitCoords, highlightCoords] 

    def createDataframe(self, index, row):

        results = []

        results.append(index)

        bindingId = str(row["bindingId"])
        pageNumber = str(row["pageNumber"])
        terms = str(row["terms"]).split(",")
        textHighlights = html.unescape(str(row["textHighlights"]))
        results.append(textHighlights)
        textHighlights = filter(None,textHighlights.replace("<em>", "").replace("</em>", "").replace('\n', '').replace('\r', '').split("###"))
        coordsAdded = False

        for alto in self.altos:
            if bindingId in alto and "page-" + pageNumber in alto:
                currentAlto = alto

                self.df.at[index, "altoPath"] = currentAlto
                results.append(currentAlto)

                #coords contain hitCoords and highlightCoords
                if textHighlights:
                    coords = self.findHitCoords(currentAlto, textHighlights, terms)

                results.append(coords[0])
                results.append(coords[1])
                coordsAdded = True
                break

        if not coordsAdded:
            results.append("")
            results.append([])
            results.append([])

        for jpg in self.jpgs:
            if str(row["bindingId"]) in jpg and "page-" + str(row["pageNumber"]) in jpg:
                results.append(jpg)
                break

        return results

    def createDataFrameProcesses(self, df, saveStateLabel, altos, jpgs, callback):

        futures = []
        self.df = df
        brokenBool = False

        self.altos = altos
        self.jpgs = jpgs

        with concurrent.futures.ProcessPoolExecutor() as executor:

            indexs = []
            rows = []
            missingNeededInformation = False

            for index, row in self.df.iterrows():
                indexs.append(index)
                rows.append(row)

            try:
                for result in executor.map(self.createDataframe, indexs, rows):
                    if len(result) == 6:
                        self.df.at[result[0], "textHighlights"] = result[1]
                        self.df.at[result[0], "altoPath"] = result[2]
                        self.df.at[result[0], "hitCoords"] = result[3]
                        self.df.at[result[0], "termRegions"] = result[4]
                        self.df.at[result[0], "jpgPath"] = result[5]
                        callback(0)
                    else:
                        callback(-1)
                        missingNeededInformation = True
                        break

            except BrokenProcessPool:
                #with open("brokenprocesspool.txt", "a") as file_object:
                #    file_object.write("broken pool!\n")
                brokenBool = True
                
                self.createDataFrameProcesses(df, saveStateLabel, altos, jpgs, callback)

        if not brokenBool and not missingNeededInformation:
            callback(1)
        else:
            callback(-1)