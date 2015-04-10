import device
import depot
import events
import gui.toggleButton
import util.connection

import collections
import matplotlib
matplotlib.use('WXAgg')
import numpy
import pylab
import Pyro4
import wx

CLASS_NAME = 'NI6036eDevice'

## Colors to use in the temperature plot
PLOT_COLORS = ['r', 'g', 'b', 'c', 'm', 'y', 'k']

## Labels to use for lines in the plot.
LEGENDS = ['X-nano', 'Y-nano', 'Z-nano', 'Stage', 'Block', 'Room']

## How we rearrange the incoming data so that it displays e.g. the nanomover
# sensors in order.

#DATA_REORDER = [1, 2, 4, 0, 5, 3]
DATA_REORDER = [0,1]


## This class speaks to the NI6036e card on the Nanomover computer. Its UI is
# all custom.
class NI6036eDevice(device.Device):
    def __init__(self):
        device.Device.__init__(self)
        # We want to delay initialization until after the power buttons system
        # is active.
        self.priority = 50
        ## IP address to connect to the computer the program is on.
        self.ipAddress = '172.16.0.20'
        ## Port the program is listening to. changed as camera is on 7767
        self.port = 7768
        ## Pyro4.Proxy for the "NI" portion of the program (mirror flips and
        # a few utility functions).
        self.niConnection = None
        ## util.connection.Connection for the temperature sensors.
        self.temperatureConnection = None
        ## util.connection.Connection for the light sensor.
        self.lightConnection = None
        
        ## Maps light modes to the mirror settings for those modes, as a list
        # of (mirror index, is up) tuples. The mirrors are:
        # 0: Front mirror in crypt
        # 1: Back mirror in crypt
        # 2: "SI" mirror in coffin
        # 5: "conventional" mirror in coffin
        self.modeToFlips = collections.OrderedDict()
        self.modeToFlips['Conventional'] = [(0, False), (1, True)]
        self.modeToFlips['Structured Illumination'] = [(0, True), (1, False)]
        self.modeToFlips['dSTORM'] = [(1, True)]
        self.modeToFlips['Inverted'] = [(2, True)]
        self.modeToFlips['Upright'] = [(2, False)]
        self.modeToFlips['with AO & 80 nm pixel size EMCCD'] = [(3, False), (4, True), (5, True)]
        self.modeToFlips['w/o AO & 209 nm pixel size EMCCD'] = [(3, True), (5, False)]
        self.modeToFlips['with AO & 80 nm pixel size sCMOS'] = [(3, False), (4, False)]
        self.modeToFlips['dSTORM straight through'] = [(1, False), (2, False), (3, True), (5, False)]
        ## List of buttons for setting the light path.
        self.lightPathButtons = []
        self.stagePathButtons = []
        self.detPathButtons = []
        ## Current light path mode.
        self.curExMode = None
        self.curStageMode = None
        self.curDetMode = None

        
        ## Matplotlib Figure of temperature data.
        self.figure = None
        ## Matplotlib canvas for the plot.
        self.canvas = None
        ## History of data we have received. Most recent datapoints are at
        # the beginning of the array.
        self.temperatureHistory = numpy.zeros((2, 10))


    ## Connect to the remote program, and set widefield mode.
    def initialize(self):
        self.niConnection = Pyro4.Proxy('PYRO:%s@%s:%d' % ('ni', self.ipAddress, self.port))
        self.temperatureConnection = util.connection.Connection(
                'temperature', self.ipAddress, self.port)
        self.temperatureConnection.connect(self.receiveTemperatureData)
#IMD 20130207 comment out as we are not using it in Oxford
#self.lightConnection = util.connection.Connection(
#                'light', self.ipAddress, self.port)
#        self.lightConnection.connect(self.receiveLightData)
        history = self.niConnection.readTempFile(10)
        if len(history):
            # Strip out the timepoints from the array; we just need the datapoints.
            history = history[:, 1:]
            # We may have fewer than 360 points here, so just copy what we
            # have.
            self.temperatureHistory = history


    ## Try to switch to widefield mode.
    def finalizeInitialization(self):
        self.setExMode('dSTORM')
        self.setStageMode('Inverted')
        self.setDetMode('w/o AO & 209 nm pixel size EMCCD')


    ## Ensure the room light status is shown.
    def makeInitialPublications(self):
#        events.publish('new status light', 'room light', '')
#        self.receiveLightData('test', not self.lightConnection.connection.getIsLightOn())
        pass

    ## Generate a column of buttons for setting the light path. Make a window
    # that plots our temperature data.
    def makeUI(self, parent):

        rowSizer=wx.BoxSizer(wx.HORIZONTAL)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(parent, -1, "Excitation path:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(label)
        for mode in ['Conventional', 'Structured Illumination', 'dSTORM']:
            button = gui.toggleButton.ToggleButton( 
                    textSize = 12, label = mode, size = (180, 50), 
                    parent = parent)
            # Respond to clicks on the button.
            wx.EVT_LEFT_DOWN(button, lambda event, mode = mode: self.setExMode(mode))
            sizer.Add(button)
            self.lightPathButtons.append(button)
            if mode == self.curExMode:
                button.activate()
        rowSizer.Add(sizer)

#IMD 20130227 - added new button stack
        stageSizer=wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(parent, -1, "Stage:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        stageSizer.Add(label)
        for mode in ['Inverted', 'Upright']:
            button = gui.toggleButton.ToggleButton( 
                    textSize = 12, label = mode, size = (180, 50), 
                    parent = parent)

            wx.EVT_LEFT_DOWN(button, lambda event, mode = mode: self.setStageMode(mode))
            stageSizer.Add(button)
            self.stagePathButtons.append(button)
            if mode == self.curStageMode:
                button.activate()
        rowSizer.Add(stageSizer)

#RK 20130227 - added new button stack
        detSizer=wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(parent, -1, "Detection path:")
        label.SetFont(wx.Font(14, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        detSizer.Add(label)
        for mode in ['with AO & 80 nm pixel size EMCCD', 'with AO & 80 nm pixel size sCMOS', 'w/o AO & 209 nm pixel size EMCCD', 'dSTORM straight through']:
            button = gui.toggleButton.ToggleButton( 
                    textSize = 12, label = mode, size = (180, 50), 
                    parent = parent)

            wx.EVT_LEFT_DOWN(button, lambda event, mode = mode: self.setDetMode(mode))
            detSizer.Add(button)
            self.detPathButtons.append(button)
            if mode == self.curDetMode:
                button.activate()
        rowSizer.Add(detSizer)

        plotFrame = wx.Frame(parent, title = "Temperature sensor plot",
                style = wx.RESIZE_BORDER | wx.FRAME_TOOL_WINDOW | wx.CAPTION)
        self.figure = matplotlib.figure.Figure((6, 4), dpi = 100,
                facecolor = (1, 1, 1))
        self.canvas = matplotlib.backends.backend_wxagg.FigureCanvasWxAgg(
                plotFrame, -1, self.figure)
        self.updatePlot()
        plotFrame.Show()
        return rowSizer


    ## Set the light path to the specified mode.
    def setExMode(self, mode):
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.lightPathButtons:
            button.setActive(button.GetLabel() == mode)
        self.curExMode = mode


    def setStageMode(self, mode):
#IMD 20130206 Oxford OMXt doesnt have a diffuser wheel
#        if mode == 'Widefield':
            # Ensure the diffuser wheel is on.
#            handler = depot.getHandlerWithName("Diffuser wheel power")
#            if not handler.getIsOn():
#                wx.MessageDialog(None,
#                        "The diffuser wheel is not active, so Widefield mode " +
#                        "is disabled.",
#                        "Can't use Widefield mode.",
#                        wx.OK | wx.STAY_ON_TOP | wx.ICON_EXCLAMATION
#                ).ShowModal()
#                self.setMode('Structured Illumination')
#                return
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.stagePathButtons:
            button.setActive(button.GetLabel() == mode)
        self.curStageMode = mode

    def setDetMode(self, mode):
        for mirrorIndex, isUp in self.modeToFlips[mode]:
            self.flipDownUp(mirrorIndex, isUp)
        for button in self.detPathButtons:
            button.setActive(button.GetLabel() == mode)
        self.curDetMode = mode


    ## Flip a mirror down and then up, to ensure that it's in the position
    # we want.
    def flipDownUp(self, index, isUp):
        self.niConnection.flipDownUp(index, int(isUp))


    ## Receive temperature data from the remote program's sensors.
    def receiveTemperatureData(self, *args):
        timepoint = args[1]
        values = args[2]
        # Push all existing data over one timepoint and insert the new
        # data at the beginning.

        length=self.temperatureHistory.shape[0]
        for i in range(self.temperatureHistory.shape[0]-1):
            self.temperatureHistory[length-i-1]=self.temperatureHistory[length-i-2]
  #      self.temperatureHistory[1:][:] = self.temperatureHistory[:-1][:]
        self.temperatureHistory[0] = list(values)
        self.updatePlot()


    ## Plot our current temperature data.
    def updatePlot(self):
        if not numpy.any(self.temperatureHistory != 0) or not self.figure:
            # No temperature data to display, or no figure to display it on.
            print "no temp data"
            return
        # Remove existing plots.
        self.figure.clear()
        axes = self.figure.gca()
        axes.set_xlabel("Minutes ago")
        axes.set_ylabel(u"Temperature (\u00b0C)")
        # Figure out how many datapoints we actually have, in the case that
        # the temperature sensor program was restarted recently and is thus
        # short on data. This is indicated by a sensor having no data (i.e.
        # still initialized to 0).
        firstZero = len(self.temperatureHistory)
#        zeros = numpy.where(self.temperatureHistory == 0)[1]
#        if len(zeros):
#            firstZero = zeros[0]
        xMin, xMax = -10, .1
        if firstZero is not None:
            xMin = -firstZero / 6.0
        yMin = self.temperatureHistory[:firstZero,0:].min()
        yMax = self.temperatureHistory[:firstZero,0:].max()
        yMin=-2
        yMax=5
        if yMax - yMin < 5:
            # Ensure the graph is at least 5 degrees tall.
            yMax += (5 - yMax + yMin) / 2.0
            yMin -= (5 - yMax + yMin) / 2.0
        axes.axis([xMin, xMax, yMin, yMax])
        xVals = numpy.arange(0, -firstZero /6.0, -.16667)
#        print xVals,self.temperatureHistory[:firstZero, 0]
        for i in xrange(0, self.temperatureHistory.shape[1]):
            axes.plot(xVals, self.temperatureHistory[:firstZero, i],
                    PLOT_COLORS[i], label = LEGENDS[i])
        self.canvas.draw()
        

    ## Receive light sensor data from the remote program's sensors.
    def receiveLightData(self, *args):
        isOn = not args[1]
        text = "Room light %s" % ['OFF', 'ON'][isOn]
        color = [(170, 170, 170), (255, 255, 0)][isOn]
 #       events.publish('update status light', 'room light', text, color)
        