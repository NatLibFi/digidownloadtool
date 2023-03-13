import tkinter as tk
from tkinter import *
from cefpython3 import cefpython as cef
import ctypes
import time
import platform

# Platforms
WINDOWS = (platform.system() == "Windows")
LINUX = (platform.system() == "Linux")
MAC = (platform.system() == "Darwin")

class CefBrowser():

    def __init__(self, parentFrame, urlChangeCallback, closeCallback, browserConnectionErrorCallback):
        cef.Initialize({"multi_threaded_message_loop": True,
        "remote_debugging_port": -1})

        # Create Browser Frame
        self.browser_frame = BrowserFrame(parentFrame)
        self.browser_frame.urlChangeCallback = urlChangeCallback
        self.browser_frame.closeCallback = closeCallback
        self.browser_frame.browserConnectionErrorCallback = browserConnectionErrorCallback
    
    def goToUrl(self, url):

        self.browser_frame.currentUrl = url
        if self.browser_frame.browser:
            self.browser_frame.browser.LoadUrl(url)

    def shutdown(self):
        cef.Shutdown()

    def close(self):
        self.browser_frame.on_root_close()

class BrowserFrame(tk.Frame):

    def __init__(self, mainframe, navigation_bar=None):
        self.navigation_bar = navigation_bar
        self.closing = False
        self.browser = None
        tk.Frame.__init__(self, mainframe)
        self.mainframe = mainframe
        self.bind("<FocusIn>", self.on_focus_in)
        self.bind("<FocusOut>", self.on_focus_out)
        self.bind("<Configure>", self.on_configure)
        """For focus problems see Issue #255 and Issue #535. """
        self.focus_set()

    def embed_browser(self):
        window_info = cef.WindowInfo()
        rect = [0, 0, self.winfo_width(), self.winfo_height()]
        window_info.SetAsChild(self.get_window_handle(), rect)
 
        def create_browser(window_info, settings, url):
            assert(cef.IsThread(cef.TID_UI))
            self.browser = cef.CreateBrowserSync(window_info=window_info,
                                settings=settings,
                                url=url)

            self.browser.SetClientHandler(LoadHandler(self))
            self.browser.SetClientHandler(LifespanHandler(self))

        # When using multi-threaded message loop, CEF's UI thread
        # is no more application's main thread. In such case browser
        # must be created using cef.PostTask function and CEF message
        # loop must not be run explicitilly.
        cef.PostTask(cef.TID_UI,
                     create_browser,
                     window_info,
                     {},
                     self.currentUrl)


    def get_window_handle(self):
        if self.winfo_id() > 0:
            return self.winfo_id()
        else:
            raise Exception("Couldn't obtain window handle")

    def message_loop_work(self):
        cef.MessageLoopWork()
        self.after(10, self.message_loop_work)

    def on_configure(self, event):
        if not self.browser:
            self.embed_browser()
        else:
            width = event.width
            height = event.height

            self.on_mainframe_configure(width, height)

    def on_root_configure(self):
        # Root <Configure> event will be called when top window is moved
        if self.browser:
            self.browser.NotifyMoveOrResizeStarted()

    def on_mainframe_configure(self, width, height):
        if self.browser:
            if WINDOWS:
                ctypes.windll.user32.SetWindowPos(
                    self.browser.GetWindowHandle(), 0,
                    0, 0, width, height, 0x0002)
            elif LINUX:
                self.browser.SetBounds(0, 0, width, height)
            self.browser.NotifyMoveOrResizeStarted()

    def on_focus_in(self, _):
        #logger.debug("BrowserFrame.on_focus_in")
        if self.browser:
            self.browser.SetFocus(True)

    def on_focus_out(self, _):
        #logger.debug("BrowserFrame.on_focus_out")
        """For focus problems see Issue #255 and Issue #535. """
        pass

    def on_root_close(self):
        #logger.info("BrowserFrame.on_root_close")
        if self.browser:
            #logger.debug("CloseBrowser")
            self.browser.CloseBrowser(True)
            self.clear_browser_references()
        else:
            #logger.debug("tk.Frame.destroy")
            self.destroy()
            

    def clear_browser_references(self):
        # Clear browser references that you keep anywhere in your
        # code. All references must be cleared for CEF to shutdown cleanly.
        self.browser = None

class LifespanHandler(object):

    def __init__(self, tkFrame):
        self.tkFrame = tkFrame

    def OnBeforeClose(self, browser, **_):
        #logger.debug("LifespanHandler.OnBeforeClose")
        if not browser.IsPopup():
            self.tkFrame.quit()
            self.tkFrame.closeCallback()

class LoadHandler(object):

    def __init__(self, browser_frame):
        self.browser_frame = browser_frame

    def OnLoadingStateChange(self, browser, **_):
        self.browser_frame.urlChangeCallback(browser.GetUrl())

    def OnLoadStart(self, browser, **_):
        self.browser_frame.urlChangeCallback(browser.GetUrl())

    def OnLoadError(self, browser, frame, error_code, error_text_out, failed_url, **_):
        # show connection error message only if error code is not -3: error code -3:An operation was aborted (due to user action).
        if error_code != -3:
            self.browser_frame.browserConnectionErrorCallback()


class FocusHandler(object):
    """For focus problems see Issue #255 and Issue #535. """

    def __init__(self, browser_frame):
        self.browser_frame = browser_frame

    def OnTakeFocus(self, next_component, **_):
        pass#logger.debug("FocusHandler.OnTakeFocus, next={next}".format(next=next_component))

    def OnSetFocus(self, source, **_):
            return True

    def OnGotFocus(self, **_):
        #logger.debug("FocusHandler.OnGotFocus")
        pass

if __name__ == '__main__':
    main()