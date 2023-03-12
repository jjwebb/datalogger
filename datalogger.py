# Bundle this app as a single executable with PyInstaller:
# pyinstaller --onefile --windowed --icon=icon.ico datalogger.py

# monitor UART input on COM5
# create GUI button to start/stop data collection
# create GUI button to clear data

import serial
import serial.tools.list_ports
import time
#import msvcrt
import tkinter as tk
import threading
import queue 
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

command = queue.Queue()
data = queue.Queue()

base_width = 800
base_height = 400

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
            plots[plotName]["plot"].legend(fontsize=6)
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
        print ("Added yline setting for " + params[0] + ": " + str(plotSettings[params[0]]["yline"]))

    if params[0] in plots:
        applyPlotSettings(params[0])


plot_width = 300
plot_height = 300
padding = 0.75

def add_plot(word):
    num_rows = int(len(plots) / max_cols) + 1
    num_cols = min(max_cols, len(plots)+1)
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
    canvas_width = num_cols * plot_width + plot_width * (num_cols - 1) * padding
    canvas_height = num_rows * plot_height + plot_height * (num_rows - 1) * padding
    window.geometry("{}x{}".format(int(base_width+canvas_width), int(base_height+canvas_height)))

    for plot, i in zip(plots.values(), range(len(plots))):
        row, col = divmod(i, num_cols)
        plot["plot"].change_geometry(num_rows, num_cols, i+1)
        plot["plot"].set_position(gs[row, col].get_position(fig))
        plot["plot"].set_subplotspec(gs[row, col])

terminals = {}

def newTerminal(name):
    terminals[name] = {}
    terminals[name]["frame"] = tk.Frame(terminals_frame)
    # space all terminals evenly
    #terminals[name]["frame"].grid(row=0, column=len(terminals))
    #terminals[name]["frame"].grid_columnconfigure(len(terminals), weight=1, uniform="terminals")
    #terminals[name]["frame"].grid(row=0, column=len(terminals), sticky="nsew")
    terminals[name]["scrollbar"] = tk.Scrollbar(terminals[name]["frame"])
    terminals[name]["scrollbar"].pack(side=tk.RIGHT, fill=tk.Y)
    terminals[name]["terminal"] = tk.Text(terminals[name]["frame"], height=10, width=5, yscrollcommand=terminals[name]["scrollbar"].set)
    terminals[name]["terminal"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    terminals[name]["scrollbar"].config(command=terminals[name]["terminal"].yview)
    terminals[name]["frame"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
    # if only one terminal, expand to fill window
    terminals[name]["frame"].pack_propagate(True if len(terminals) == 1 else False)

    # configure terminal frames to resize evenly
    # for i in range(len(terminals)):
    #     terminals_frame.grid_columnconfigure(i, weight=1, uniform="terminals")
    # for i, terminal in enumerate(terminals.values()):
    #     terminal["frame"].grid_columnconfigure(i, weight=1, uniform="terminals")

def logToTerminal(terminalName, message):
    if terminalName not in terminals:
        newTerminal(terminalName)
    terminal = terminals[terminalName]["terminal"]
    terminal.insert(tk.END, message)
    terminal.see(min(tk.END, terminal.index("end-1c")))

def data_callback():
    global points
    while True:
    #if not data.empty():
        message: str = data.get(block=True)
        params = message.split()
        timestamp = time.strftime("[%H:%M:%S", time.localtime()) + ".{:03d}]".format(round(time.time() * 1000) % 1000)

        if len(params) == 1:
            logToTerminal("main", timestamp + " " + message)

        # if there are at least two terms in the message and the 2nd term is a custom setting, add it
        elif params[1] in customSettings:
            addPlotSetting(message)
            logToTerminal("main", timestamp + " " + message)

        # if the message is 2 or 3 terms long, and the 2nd term is a number, plot it
        elif 1 < len(params) < 4: 
            word, value, *extraTerm = params
            if points % 20 == 0 and send_test_messages.get():
                word = word + str(points // 20)
            value = getNumber(value)
            if word.isalnum() and value is not None:
                #print("Plotting! " + word + " " + value)
                if word not in plots:
                    add_plot(word)
                    newTerminal(word)

                logToTerminal(word, timestamp + " " + message)
                #plots[word]["plot"].plot(time.time(), value, 'bo')
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
    #window.after(1, data_callback)

def serialPoll(baud_rate, serial_port):
    #baud = int(baud_rate.get())
    #baud = baud_rate.get()
    
    ser = serial.Serial()
    if ser.isOpen():
        ser.close()
    # try:
    #     ser = serial.Serial(None, baud_rate, timeout=0.02)
    # except:
    #     data.put("error serial port: " + ser.port + "\n")
    #     return
    #ser.flush()
    last_send = time.time()

    while (True):
        if not command.empty():
                cmd = command.get()
                if cmd == "start" and not ser.isOpen():
                    #ser.port = serial_port
                    try:
                        # set baud rate, serial port, and timeout
                        ser.baudrate = baud_rate()
                        print("Baud type: " + str(type(baud_rate())))
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
                else:
                    print("ser.isOpen(): " + str(ser.isOpen()))
                    print("unknown command: " + cmd)
    
        if ser.isOpen():
            if ser.in_waiting > 0:
                #line = ser.readline().decode('utf-8').rstrip()
                line = ser.readline().decode('utf-8', errors='ignore').rstrip()
                if (line != ""):
                    data.put((line+"\n") if line[-1] != "\n" else line)
            else:
                time.sleep(0.001)
            # send a character to the serial port if time since last send is > 1 second
            if send_test_messages.get() and time.time() - last_send > 0.1:
                ser.write(b'helloWorld ' + str.encode(str(time.time())))
                last_send = time.time()
        else:
            time.sleep(0.1) # pause so we don't eat up CPU cycles (CPU usage spikes without this)
        
        # if stop():
        #     print("stopping serial poll!")
        #     break

    #window.after(100, serialPoll)

plots = {}
points = 1

max_cols = 3  # Change this to the number of columns you want

# num_cols = min(max_cols, len(plots))
# num_rows = int(len(plots) / max_cols) + 1
# gs = gridspec.GridSpec(num_rows, num_cols)
# gs.update(hspace=0.5, wspace=0.5)  # Change these values to adjust spacing and padding

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
    global plots, points, fig, terminals
    terminals["main"]["terminal"].delete(1.0, tk.END)

    # delete all terminals except main
    for terminal in terminals:
        if terminal != "main":
            terminals[terminal]["frame"].destroy()
            #del terminals[terminal]
    terminals = {"main": terminals["main"]}

    plots = {}
    # clear the figure
    fig.clf()
    # reset size of window
    window.geometry("{}x{}".format(base_width, base_height))
    points = 1
    canvas.draw()
    
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

## TERMINALS ##

# create a terminal window that will display the data
terminals_frame = tk.Frame(window)
#terminals_frame.grid()
terminals_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)


# terminal_scrollbar = tk.Scrollbar(terminal_frame)
# terminal_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

# terminal = tk.Text(terminal_frame, height=10, width=80, yscrollcommand=terminal_scrollbar.set)
# terminal.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# terminal_scrollbar.config(command=terminal.yview)

# START THREAD FOR SERIAL POLLING #

thread = threading.Thread(target=serialPoll, args=(lambda: baud_rate.get(), lambda: serial_port.get()), daemon=True)
thread.start()

dataThread = threading.Thread(target=data_callback, daemon=True)
dataThread.start()

newTerminal("main")

figW = 5
figH = 4
fig = plt.Figure(figsize=(figW, figH), dpi=100)
fig.tight_layout()
canvas = FigureCanvasTkAgg(fig, master=window)
canvas.draw()
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)



#window.after(10, data_callback)

# start the GUI window
window.mainloop()

command.put("quit")

# pause for 1 second
time.sleep(0.2)