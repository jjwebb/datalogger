# Bundle this app as a single executable with PyInstaller:
# pyinstaller --onefile --windowed --icon=icon.ico --add-data 'buttons.json:.' datalogger.py
# if not on $PATH:
# python -m PyInstaller --onefile --windowed --icon=icon.ico --add-data 'buttons.json;.' datalogger.py

# monitor UART input on COM port

import json
import os
from os import path
import serial
import serial.tools.list_ports
import time
import tkinter as tk
import threading
import queue 
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.style as mplstyle
mplstyle.use('fast')

command = queue.Queue()
data = queue.Queue()

base_width = 820
base_height = 300

# create a GUI window
window = tk.Tk()
window.title("Serial Data Grapher / Logger")
window.geometry("{}x{}".format(base_width, base_height))

# create a button to start/stop data collection
def start_stop():
    if start_stop_button["text"] == "Start":
        start_stop_button["text"] = "Stop"
        command.put("start")
    else:
        start_stop_button["text"] = "Start"
        command.put("stop")

def getNumber(string):
    try:
        return int(string)
    except:
        try:
            return float(string)
        except:
            return None

plotSettings = {}

def applyPlotSettings(plotName):
    if plotName not in plotSettings:
        return
    
    if "yline" in plotSettings[plotName]:
        for name, settings in plotSettings[plotName]["yline"].items():
            lines = plots[plotName]["plot"].get_lines()
            for line in lines:
                if line.get_label() == name:
                    line.remove()
            plots[plotName]["plot"].axhline(y=settings["value"], color=settings["color"], label=name)
            plots[plotName]["plot"].legend(fontsize=6, loc="upper right")
            print ("Applied yline setting for " + plotName + ": " + str(plotSettings[plotName]["yline"]))

# list of parameters to check for in the message
customSettings = ["yline"]

# This will take the message input and check for custom parameters
def addPlotSetting(message: str):
    params = message.split()

    if len(params) < 3:
        return
    
    # variableName yline [value] [name] [color]
    if len(params) < 6 and params[1] == "yline" and getNumber(params[2]) is not None:
        if params[0] not in plotSettings:
            plotSettings[params[0]] = {}
        if "yline" not in plotSettings[params[0]]:
            plotSettings[params[0]]["yline"] = {}
        # create a new line object with the value given
        line = {"value": getNumber(params[2])}
        # get the name of the line from the message, or use 'Line[num]' if not given
        name = params[3] if len(params) > 3 else f"Level{len(plotSettings[params[0]]['yline'])}"
        # get the color of the line from the message, or use 'blue' if not given
        line["color"] = params[4] if len(params) > 4 else "blue"
        # add the line to the plot settings by name
        plotSettings[params[0]]["yline"][name] = line
        #print ("Added yline setting for " + params[0] + ": " + str(plotSettings[params[0]]["yline"]))

    if params[0] in plots:
        applyPlotSettings(params[0])


plot_width = 380
plot_height = 400
padding = 0.75

plots_width = 0
plots_height = 0
terminal_height = 0

def add_plot(word):
    global base_width, base_height, plots_width, plots_height, terminal_height

    num_rows = int(len(plots) / MAX_PLOT_COLS) + 1
    num_cols = min(MAX_PLOT_COLS, len(plots)+1)
    print("num_rows: " + str(num_rows) + " num_cols: " + str(num_cols))
    #gs = gridspec.GridSpec(num_rows, num_cols)
    #fig.set_figwidth(num_cols * figW)
    #fig.set_figheight(num_rows * figH)
    gs = gridspec.GridSpec(num_rows, num_cols)
    gs.update(hspace=0.5, wspace=0.25)  # Change these values to adjust spacing and padding

    row, col = divmod(len(plots), num_cols)
    print("row: " + str(row) + " col: " + str(col))
    plots[word] = {"len": 0}
    plots[word]["plot"] = fig.add_subplot(gs[row, col])
    plots[word]["plot"].set_title(word)
    plots[word]["plot"].set_xlabel('Reading #')
    plots[word]["plot"].set_ylabel('Value')
    # Prevent the graphs from using scientific notation and offsets
    plots[word]["plot"].ticklabel_format(useOffset=False, style='plain')

    # apply any custom settings, if defined
    applyPlotSettings(word)

    # calculate size of canvas and set window geometry
    plots_width = num_cols * plot_width
    plots_height = num_rows * plot_height
    window.geometry("{}x{}".format(int(base_width + plots_width), 
                                   int(base_height + plots_height + terminal_height)))

    for plot, i in zip(plots.values(), range(len(plots))):
        row, col = divmod(i, num_cols)
        plot["plot"].set_position(gs[row, col].get_position(fig))
        plot["plot"].set_subplotspec(gs[row, col])

    # fig.canvas.draw()
    # fig.canvas.flush_events()

terminals = {}
terminals_frame = tk.Frame(window)
MAX_TERMINAL_COLS = 4
TERMINAL_WIDTH = 60
TERMINAL_HEIGHT = 8

def newTerminal(name):
    global base_width, base_height, plots_width, plots_height, terminal_height
    row, col = divmod(len(terminals), MAX_TERMINAL_COLS)

    terminals[name] = {}
    terminals[name]["frame"] = tk.Frame(terminals_frame)
    terminals[name]["scrollbar"] = tk.Scrollbar(terminals[name]["frame"])
    terminals[name]["scrollbar"].pack(side=tk.RIGHT, fill=tk.Y)
    terminals[name]["terminal"] = tk.Text(terminals[name]["frame"], height=TERMINAL_HEIGHT, width=TERMINAL_WIDTH, yscrollcommand=terminals[name]["scrollbar"].set)
    terminals[name]["terminal"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    terminals[name]["scrollbar"].config(command=terminals[name]["terminal"].yview)

    terminals[name]["frame"].grid(row=row, column=col, sticky="nsew")

    # Configure the column and row weights
    terminals_frame.grid_columnconfigure(col, weight=1)
    terminals_frame.grid_rowconfigure(row, weight=1)


def logToTerminal(terminalName, message):
    if terminalName not in terminals:
        newTerminal(terminalName)
    terminal = terminals[terminalName]["terminal"]
    terminal.insert(tk.END, message)
    terminal.see(min(tk.END, terminal.index("end-1c")))

testVarNum = 0
def data_callback():
    global points, testVarNum
    while True:
    #if not data.empty():
        message: str = data.get(block=True)
        params = message.split()
        timestamp = time.strftime("[%H:%M:%S", time.localtime()) + ".{:03d}]".format(round(time.time() * 1000) % 1000)

        numParams = len(params)
        if numParams == 1:
            logToTerminal("main", timestamp + " " + message)

        # if there are at least two terms in the message and the 2nd term is a custom setting, add it
        elif params[1] in customSettings:
            addPlotSetting(message)
            logToTerminal("main", timestamp + " " + message)

        # if the message is 2 or 3 terms long, and the 2nd term is a number, plot it
        elif 1 < numParams < 4: 
            word, value, *extraTerm = params

            value = getNumber(value)
            if word.isalnum() and value is not None:
                if word not in plots:
                    add_plot(word)
                    newTerminal(word)

                logToTerminal(word, timestamp + " " + message)
                plots[word]["len"] += 1

                # plot the value as a blue point, or as a green point if any extra modifier term is present
                plots[word]["plot"].plot(plots[word]["len"], value, 'go' if extraTerm == [] else 'bo')
                points+=1

                canvas.draw()
            else:
                logToTerminal("main", timestamp + " " + message)
        elif message.lower().startswith("error"):
            start_stop_button["text"] = "Start"
            logToTerminal("main", timestamp + " " + message)
            #command.put("stop")
        else:
            logToTerminal("main", timestamp + " " + message)

        if save_to_file.get():
                    print("saving to file!")
                    f = open("TTL.txt", "a", newline='\n')
                    f.write(timestamp + " " + message)  
                    f.close()
            
def serialPoll(baud_rate, serial_port):
    testMessages = 0
    
    ser = serial.Serial()

    if ser.isOpen():
        ser.close()

    last_send = time.time()

    while (True):
        if not command.empty():
                cmd = command.get()
                if cmd == "start" and not ser.isOpen():
                    try:
                        # set baud rate, serial port, and timeout
                        ser.baudrate = baud_rate()
                        print("Baud: " + str(baud_rate()))
                        print("opening serial port: " + serial_port())
                        ser.port = serial_port()
                        ser.timeout = 0.02
                        ser.open()
                    except:
                        data.put("error opening serial port: " + ser.port + "\n")
                elif cmd == "stop":
                    print("closing serial port: " + ser.port)
                    ser.close()
                elif cmd == "quit":
                    print("quitting serial thread!")
                    ser.close()
                    break
                elif type(cmd) == int:
                    if ser.isOpen():
                        ser.write(cmd.to_bytes(1, byteorder='big'))
                        #print("sending: " + str(cmd))
                        #ser.write(cmd)
                else:
                    print("ser.isOpen(): " + str(ser.isOpen()))
                    print("unknown command: " + cmd)
    
        if ser.isOpen():
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').rstrip()
                if (line != ""):
                    data.put((line+"\n") if line[-1] != "\n" else line)
            else:
                time.sleep(0.001)
            # send a character to the serial port if time since last send is > 1 second
            if send_test_messages.get() and time.time() - last_send > 0.2:
                i = testMessages // 20
                testMessages += 1
                ser.write(str.encode(f'helloWorld{i} ' + str(time.time())))
                last_send = time.time()
        else:
            time.sleep(0.1) # pause so we don't eat up CPU cycles (CPU usage spikes without this)
        
        # if stop():
        #     print("stopping serial poll!")
        #     break

plots = {}
points = 1
MAX_PLOT_COLS = 3  # Change this to the number of columns you want

## FRAME FOR BUTTONS ##

buttonFrame = tk.Frame(window)
buttonFrame.pack(side=tk.TOP, anchor="w", padx=5, pady=5)

## START/STOP BUTTON ##

start_stop_button = tk.Button(buttonFrame, text="Start", command=start_stop)
start_stop_button.pack(side=tk.LEFT, padx=5, pady=5)


## SERIAL PORT DROPDOWN MENU ##

# dropdown menu to select the serial port
ports = serial.tools.list_ports.comports()

# Create a dictionary mapping port descriptions to device strings
port_dict = {port.description: port.device for port in ports}

# Set the value of serial_port to the corresponding device string
def on_port_select(port_description):
    serial_port.set(port_dict[port_description])
    # If logger is running, stop and restart it to use the new port
    if start_stop_button["text"] == "Stop":
        command.put("stop")
        command.put("start")

# Create the dropdown menu
serial_port = tk.StringVar()
serial_port.set(list(port_dict.values())[0])  # Set default value to first port description
tk.Label(buttonFrame, text="Port:").pack(side=tk.LEFT, padx=5, pady=5)
port_menu = tk.OptionMenu(buttonFrame, serial_port, *port_dict.keys(), command=on_port_select)
port_menu.pack(side=tk.LEFT, padx=5, pady=5)


## BAUD RATE DROPDOWN MENU ##

# dropdown menu to select the baud rate
baud_rates = [9600, 19200, 38400, 57600, 115200]

# Set the value of baud_rate to the corresponding baud rate string
def on_baud_select(rate):
    baud_rate.set(rate)
    # If logger is running, stop and restart it to apply the new baud rate
    if start_stop_button["text"] == "Stop":
        command.put("stop")
        command.put("start")

# Create the dropdown menu
baud_rate = tk.StringVar()
baud_rate.set(baud_rates[0])  # Set default value to first baud rate
tk.Label(buttonFrame, text="Baud:").pack(side=tk.LEFT, padx=5, pady=5)
baud_menu = tk.OptionMenu(buttonFrame, baud_rate, *baud_rates, command=on_baud_select)
baud_menu.pack(side=tk.LEFT, padx=5, pady=5)


## CLEAR BUTTON ##

# create a button to clear data
def clear():
    global plots, points, fig, terminals, plots_width, plots_height, terminal_height
    terminals["main"]["terminal"].delete(1.0, tk.END)

    # delete all terminals except main
    for terminal in terminals:
        if terminal != "main":
            terminals[terminal]["frame"].destroy()
    terminals = {"main": terminals["main"]}

    plots = {}
    # clear the figure
    fig.clf()
    # reset size of window
    window.geometry("{}x{}".format(base_width, base_height))
    points = 1

    canvas.draw()

    # Reset the grid configuration for rows and columns
    for i in range(MAX_TERMINAL_COLS):
        terminals_frame.grid_columnconfigure(i, weight=0)
        terminals_frame.grid_rowconfigure(i, weight=0)
    terminals_frame.grid_columnconfigure(0, weight=1)
    terminals_frame.grid_rowconfigure(0, weight=1)
    
clear_button = tk.Button(buttonFrame, text="Clear", command=clear)
clear_button.pack(side=tk.LEFT, padx=5, pady=5)

## SAVE TO FILE CHECKBOX ##

# create a checkbox to enable/disable save to file
save_to_file = tk.BooleanVar()
#save_to_file = False
save_to_file_checkbox = tk.Checkbutton(buttonFrame, text="Save to file", variable=save_to_file)
save_to_file_checkbox.pack(side=tk.LEFT, padx=5, pady=5)

## SEND TEST MESSAGES CHECKBOX ##

# create a checkbox to send test messages
send_test_messages = tk.BooleanVar()
send_test_messages_checkbox = tk.Checkbutton(buttonFrame, text="Send test messages", variable=send_test_messages)
send_test_messages_checkbox.pack(side=tk.LEFT, padx=5, pady=5)


## ACTION BUTTONS ##

def rearrange_buttons(event):
    window_width = window.winfo_width()
    min_button_width = 120  # Change to make buttons fit in window
    num_of_columns = window_width // min_button_width

    # Rearrange the buttons
    for index, button in enumerate(buttons_frame.winfo_children()):
        row, col = divmod(index, num_of_columns)
        button.grid(row=row, column=col, padx=5, pady=5)

def create_buttons(buttons):
    for label, value in buttons.items():
        button = tk.Button(buttons_frame, text=label, command=lambda v=value: command.put(v))
        button.pack_forget()

buttonsFile = path_to_dat = path.abspath(path.join(path.dirname(__file__), 'buttons.json'))

# If buttons.json exists, create buttons from the file. Otherwise, this section will be skipped.
if (path.isfile(buttonsFile)):
    # open JSON file and read the label and corresponding action number for each button
    with open(buttonsFile) as f:
        buttons = json.load(f)

    buttons_frame = tk.Frame(window)
    buttons_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

    create_buttons(buttons)
    window.bind('<Configure>', rearrange_buttons)


## TERMINALS ##

# create a frame for terminals that will display the data
terminals_frame = tk.Frame(window)
terminals_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)

# START THREAD FOR SERIAL POLLING #

thread = threading.Thread(target=serialPoll, args=(lambda: baud_rate.get(), lambda: serial_port.get()), daemon=True)
thread.start()

dataThread = threading.Thread(target=data_callback, daemon=True)
dataThread.start()

newTerminal("main")

figW = 5
figH = 4
#fig = plt.Figure(figsize=(figW, figH), dpi=100)
fig = plt.Figure()
fig.tight_layout()
canvas = FigureCanvasTkAgg(fig, master=window)
# set size of the canvas
canvas.get_tk_widget().config(width=figW*100, height=figH*300)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

# start the GUI window
window.mainloop()

command.put("quit")

# pause for 1 second
time.sleep(0.2)