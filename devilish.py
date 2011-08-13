#!/usr/bin/env python

# Author:
#   Iye Cba <iye {dot} cba {at} gmail {dot} com>
#   https://github.com/iye/devilish

# Devilish 0.7b
# devilish.py - PyGTK App for monitoring log files realtime. It uses inotify to
# detect file modifications and when an appended line has a string you are
# interested in, it will alert you via your notification daemon and with an icon
# in the tray.

#   License:
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#   MA 02110-1301, USA.



# Icons taken from Gnome Icon Theme



#TODO: implement regexp for complex filters? 
#TODO: Move all code to open/save config.cfg to it's own class
#TODO: right click on icontray displays "Quit" option
#TODO: configparser sucks, deletes comments when saving setting to config file, replace.
#TODO: "Copy to clipboard" option when right clicking on the log treeview        
#TODO: coding style, docstings...



import gtk
import pyinotify
import pynotify
import ConfigParser
import os

class  Devilish:

    def __init__(self):
        gladefilename = "devilish.glade"
        builder = gtk.Builder()
        builder.add_objects_from_file(gladefilename,
        ["window1", "statusicon1", "liststore1", "image1", "image2"])
        builder.connect_signals(self)

        #widgets
        self.window = builder.get_object('window1')
        self.liststore = builder.get_object('liststore1')
        self.modelfilter = self.liststore.filter_new()
        self.statusicon = builder.get_object('statusicon1')
	    #Specify the function that determines which rows to filter out and which ones to display
        self.modelfilter.set_visible_func(self.filtertree, data=None)
        self.treeview = builder.get_object('treeview1')
        #Assign the filter as our tree's model
        self.treeview.set_model(self.modelfilter)
        self.searchbox = builder.get_object('entry1')


        #needed for starting and stoping pyinotify from any method
        self.wm = None
        self.notifier = None

        #Handler of the opened log file
        self.file = None
        #File path and name
        self.filename = None
        
        #filterwordlist will contain the strings to search in each line added to the log.
        self.filterwordlist = None

        # Load icons to display in statusicon
        # 0 if face-devilish.png (aka nothing new in the log)
        # 1 if face-angry.png (aka something new in the log)
        self.icon_in_tray = 0
        self.icon_allfine_pixbuf = gtk.gdk.pixbuf_new_from_file("icons/face-devilish.png")
        self.icon_alert_pixbuf = gtk.gdk.pixbuf_new_from_file("icons/face-angry.png")

        #Show notify daemon bubble?
        self.show_notify_bubble = 1

        #Load setting from config.cfg
        self.load_settings()


    def load_settings(self):
        #Load config file
        config = ConfigParser.RawConfigParser()
        config.read(['config.cfg', os.path.expanduser('~/.config/pylogwatch/myapp.cfg')])
        
        #Path of file to open
        self.filename = config.get("Main", "logfilePath")
        
        #Filter strings, convert string to list
        var = config.get("Main", "filterStrings")
        var = var.strip('\"')
        self.filterwordlist = var.split('\", \"')

        self.show_notify_bubble = config.get("Main", "notifybubble")


    #Open filterdialog on Menu->Edit->"Search Strings"
    def on_filter_words_dialog_open(self, widget):
        filterdialog = FilterDialog(self)

        
    #Filter for the quick search box
    def filtertree(self, model, iter, data):
        searchboxtext = self.searchbox.get_text()
        if (searchboxtext == ""):
            return True
        logline = str(model.get_value(iter, 0))
        if (logline.find(searchboxtext) > -1):
            return True
        else:
            return False
    
    #Called when the quick search box entry1 has some modification
    def on_entry1_changed(self, widget):
        self.modelfilter.refilter()
    
    #On/Off button        
    def on_togglebutton1_toggled(self, widget, data=None):
        if self.notifier.isAlive(): self.notifier.stop()
        else: self.watch_log()

    #Clear listore on click
    def on_clearbutton_clicked(self, widget, data=None):
        self.liststore.clear()

    #Check if file specified in config file exists, if not, show File Chooser dialog.
    def startup_file_selection(self, filepath):
        try:
            tryfile = open(filepath)
            self.filename = tryfile.name
        except:
            print(filepath, "Not found, check if you have read access to that file")
        
        if self.filename == None:
            self.on_open_menu_item_activate(self)
        else:
            self.watch_log()

    def main(self):
        #This makes threads work in gtk. Pyinotify thread wont work without this
        gtk.gdk.threads_init()
        self.window.show()
        #File selection dialog will show up only if logfilePath is pointing to non existant file.
        self.startup_file_selection(self.filename)
        gtk.main()

    def on_window1_destroy(self, widget, data=None):
        #Stop pyinotifier thread        
        try: self.notifier.stop()
        except: pass
        gtk.main_quit()
        return False
        
    #What to do when the icon in tray is pressed.
    def on_statusicon1_button_press_event(self, widget, data=None):
        self.hide_show_window()


    def hide_show_window(self):
        #visible = self.window.get_property("visible")
        visible = self.window.is_active()
        #if visible:
        if visible == True:
            self.window.hide()
            self.statusicon.set_from_pixbuf(self.icon_allfine_pixbuf)
        else:
            self.window.show()
            self.window.deiconify()
            self.statusicon.set_from_pixbuf(self.icon_allfine_pixbuf)     


    #Capture Iconify event (iconify=minimize)
    def on_window_state_event(self, widget, event):
        if event.changed_mask & gtk.gdk.WINDOW_STATE_ICONIFIED:
            if event.new_window_state & gtk.gdk.WINDOW_STATE_ICONIFIED:
                #window was minimized if it arrives here
                self.window.hide()
                self.statusicon.set_from_pixbuf(self.icon_allfine_pixbuf)


    #Select log file to monitor.
    def on_open_menu_item_activate(self, widget, data=None):
        chooser = gtk.FileChooserDialog("Open File...", self.window,
                                        gtk.FILE_CHOOSER_ACTION_OPEN,
                                        (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, 
                                         gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            self.filename = chooser.get_filename()
            #stop notifier if working
            if self.notifier != None: self.notifier.stop()
        else:
            self.filename = None
            chooser.destroy()
            self.on_open_menu_item_activate(self)
            
        chooser.destroy()
        if self.filename: self.watch_log()


    #Open log file and start pyinotify thread.
    def watch_log(self):
        try:
            self.file = open(self.filename)
        except:
            print "Error opening log file"
            self.on_open_menu_item_activate(self)
        self.file.seek(0,2)
        self.wm = pyinotify.WatchManager()
        self.notifier = pyinotify.ThreadedNotifier(self.wm, EventHandler())
        self.notifier.start()
        self.wm.add_watch(self.filename, pyinotify.IN_MODIFY)


    def show_about_dialog(self, widget):
        aboutdlg = AboutDialog()

    #called when modification is detected by pyinotify
    def log_change_action(self,event):
        #read line in log and append to liststore if it has wanted string
        #file.readline will return empty string if it reachs EOF.
        line = self.file.readline()
        while line != "":
            for item in self.filterwordlist:
                if line.find(item) > 0:
                    line = line.rstrip('\n')
                    linetime=line[0:15]
                    linelog=line[16:]
                    #Change icon in tray to one showing a warning
                    if self.icon_in_tray == 0:
                        self.statusicon.set_from_pixbuf(self.icon_alert_pixbuf)
                    #if window is active, don't show notifications
                    window_isactive = self.window.is_active()
                    if (self.show_notify_bubble == "1" and 
                        window_isactive != True):
                        n = pynotify.Notification(linetime, linelog)
                        n.show()
                    #Code to autoscroll treeview
                    #app.liststore.append([linelog, linetime]) #uncomment this
                    # and disable following 3 lines to disable autoscroll
                    row_iter = app.liststore.append([linelog, linetime])
                    path = app.liststore.get_path(row_iter)
                    self.treeview.scroll_to_cell(path)
                    break
            line = self.file.readline()


class EventHandler(pyinotify.ProcessEvent):
    def process_IN_MODIFY(self, event):
        #what to do in "modify" event 
        app.log_change_action(event)


class AboutDialog():
    def __init__(self):
        gladefilename = "devilish.glade"
        builder = gtk.Builder()
        builder.add_objects_from_file(gladefilename, ["aboutdialog1"])
        self.aboutdlg = builder.get_object("aboutdialog1")
        self.aboutdlg.connect("response", self.hide_about)
        self.aboutdlg.show()

    def hide_about(self, widget, data=None):
        self.aboutdlg.hide()
        return True


class FilterDialog():
    #TODO: Maybe I should just ask users to open config.cfg
    # and let them edit the prefs there :)
    def __init__(self, parent_window):
        
        #Load glade file for filterdialog
        gladefilename = "dialog.glade"
        builder = gtk.Builder()
        builder.add_from_file(gladefilename)
        builder.connect_signals(self)

        self.filterwordsdialog = builder.get_object("dialog1")
        self.filterwords_textview = builder.get_object("textview1")

        #To be able to access members of parent window
        self._parent_window = parent_window
        
        #Convert list to string so we can then convert it to gtk.textbuffer.
        #Gtk.textview uses gtk.textbuffer for showing text.
        try:
            filterlist_string = '\n'.join(map(str, self._parent_window.filterwordlist))
        except:
            print "Error, could not convert Filter List to String"
   
        self.filterwords_textview.get_buffer().set_text(filterlist_string)
        self.filterwordsdialog.show()

    def on_button_accept_dialog1_clicked(self, widget):
        textbuffer = self.filterwords_textview.get_buffer()
        string_of_buffer = textbuffer.get_text(*textbuffer.get_bounds())
        self._parent_window.filterwordlist = string_of_buffer.split("\n")
        self.filterwordsdialog.destroy()


        #Save filters to config file
        config = ConfigParser.RawConfigParser()
        config.read(['config.cfg', os.path.expanduser('~/.config/devilish/config.cfg')])
        var = '\"' + string_of_buffer + '\"'
        var = var.replace('\n','\", \"')
        config.set('Main', 'filterStrings', var)
        #?? fix, is this writting to the config.cfg in current dir when maybe the
        #one in ./config/devilish is being used.
        with open('config.cfg', 'wb') as configfile:
            config.write(configfile)        


    def on_button_dialog1_cancel_clicked(self, widget):
        self.filterwordsdialog.destroy()


if __name__ == "__main__":
     app = Devilish()
     app.main()
