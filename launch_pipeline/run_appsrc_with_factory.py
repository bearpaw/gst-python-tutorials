import sys
import traceback
import argparse
import typing as typ
import random
import time
from fractions import Fraction

import numpy as np


import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GObject  # noqa:F401,F402
from gi.repository import GstVideo
# from gstreamer import GstContext, GstPipeline, GstApp, Gst, GstVideo, GLib, GstVideoSink
import gstreamer.utils as utils

VIDEO_FORMAT = "RGB"
WIDTH, HEIGHT = 640, 480
FPS = Fraction(30)
GST_VIDEO_FORMAT = GstVideo.VideoFormat.from_string(VIDEO_FORMAT)

def bus_call(bus, message, loop):
    t = message.type
    if t == Gst.MessageType.EOS:
        sys.stdout.write("End-of-stream\n")
        loop.quit()
    elif t==Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n" % (err, debug))
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        sys.stderr.write("Error: %s: %s\n" % (err, debug))
        loop.quit()
    return True


def fraction_to_str(fraction: Fraction) -> str:
    """Converts fraction to str"""
    return '{}/{}'.format(fraction.numerator, fraction.denominator)


def parse_caps(pipeline: str) -> dict:
    """Parses appsrc's caps from pipeline string into a dict

    :param pipeline: "appsrc caps=video/x-raw,format=RGB,width=640,height=480 ! videoconvert ! autovideosink"

    Result Example:
        {
            "width": "640",
            "height": "480"
            "format": "RGB",
            "fps": "30/1",
            ...
        }
    """

    try:
        # typ.List[typ.Tuple[str, str]]
        caps = [prop for prop in pipeline.split(
            "!")[0].split(" ") if "caps" in prop][0]
        return dict([p.split('=') for p in caps.split(',') if "=" in p])
    except IndexError as err:
        return None

pts = 0  # buffers presentation timestamp
duration = 10**9 / (FPS.numerator / FPS.denominator)  # frame duration
def need_data_handle(appsrc, length): #udata):
    global pts, duration
    print("start feed {}".format(pts))
    # create random np.ndarray
    array = np.random.randint(low=0, high=255,
                                size=(HEIGHT, WIDTH, CHANNELS), dtype=DTYPE)

    # convert np.ndarray to Gst.Buffer
    gst_buffer = utils.ndarray_to_gst_buffer(array)

    # set pts and duration to be able to record video, calculate fps
    pts += duration  # Increase pts by duration
    gst_buffer.pts = pts
    gst_buffer.duration = duration

    # emit <push-buffer> event with Gst.Buffer
    appsrc.emit("push-buffer", gst_buffer)
    
def enough_data_handle(appsrc, length):
    print("stop feed")

FPS_STR = fraction_to_str(FPS)
DEFAULT_CAPS = "video/x-raw,format={VIDEO_FORMAT},width={WIDTH},height={HEIGHT},framerate={FPS_STR}".format(**locals())

# Converts list of plugins to gst-launch string
# ['plugin_1', 'plugin_2', 'plugin_3'] => plugin_1 ! plugin_2 ! plugin_3
DEFAULT_PIPELINE = utils.to_gst_string([
    "appsrc emit-signals=True is-live=True caps={DEFAULT_CAPS}".format(**locals()),
    "queue",
    "videoconvert",
    "autovideosink"
])


ap = argparse.ArgumentParser()
ap.add_argument("-p", "--pipeline", required=False,
                default=DEFAULT_PIPELINE, help="Gstreamer pipeline without gst-launch")

ap.add_argument("-n", "--num_buffers", required=False,
                default=100, help="Num buffers to pass")

args = vars(ap.parse_args())

command = args["pipeline"]

args_caps = parse_caps(command)
NUM_BUFFERS = int(args['num_buffers'])

WIDTH = int(args_caps.get("width", WIDTH))
HEIGHT = int(args_caps.get("height", HEIGHT))
FPS = Fraction(args_caps.get("framerate", FPS))

GST_VIDEO_FORMAT = GstVideo.VideoFormat.from_string(
    args_caps.get("format", VIDEO_FORMAT))
CHANNELS = utils.get_num_channels(GST_VIDEO_FORMAT)
DTYPE = utils.get_np_dtype(GST_VIDEO_FORMAT)

FPS_STR = fraction_to_str(FPS)
CAPS = "video/x-raw,format={VIDEO_FORMAT},width={WIDTH},height={HEIGHT},framerate={FPS_STR}".format(**locals())

# with GstContext():  # create GstContext (hides MainLoop)

# create pipeline
pipeline = Gst.Pipeline()
    
# create appsrc
appsrc = Gst.ElementFactory.make("appsrc", "appsrc")
# instructs appsrc that we will be dealing with timed buffer
appsrc.set_property("format", Gst.Format.TIME)

# instructs appsrc to block pushing buffers until ones in queue are preprocessed
# allows to avoid huge queue internal queue size in appsrc
appsrc.set_property("block", True)

# set input format (caps)
appsrc.set_caps(Gst.Caps.from_string(CAPS))
appsrc.set_property("emit-signals", True)

appsrc.connect("need-data", need_data_handle)
appsrc.connect("enough-data", enough_data_handle)

queue = Gst.ElementFactory.make("queue","queue")
convertor = Gst.ElementFactory.make("videoconvert", "convertor")
autovideosink = Gst.ElementFactory.make("autovideosink", "autovideosink")

# add to pipeline
pipeline.add(appsrc)
pipeline.add(queue)
pipeline.add(convertor)
pipeline.add(autovideosink)

# link elements
appsrc.link(queue)
queue.link(convertor)
convertor.link(autovideosink)

 # create an event loop and feed gstreamer bus mesages to it
loop = GObject.MainLoop()
bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect ("message", bus_call, loop)

print("Starting pipeline \n")
# start play back and listed to events		
pipeline.set_state(Gst.State.PLAYING)
try:
    loop.run()
except:
    pass
# cleanup
print("Exiting app\n")
pipeline.set_state(Gst.State.NULL)
