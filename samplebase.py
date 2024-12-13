#!/usr/bin/python3
from samplebase import SampleBase
from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
from PIL import Image
import time
from datetime import datetime
import json
import signal
import sys
import requests
import io
from os import path
import configparser
import feedparser
import dateparser
import numpy as np


class rss:
    def __init__(self):
        self.limit = 12 * 3600 * 1000
        self.current_time_millis = lambda: int(round(time.time() * 1000))
        self.current_timestamp = self.current_time_millis()
        self.posts = {}

    #
    # function to determine if post is in db
    #
    def post_is_in_db(self, title):
        if title in self.posts.keys():
            return True
        else:
            return False

    # return true if the title is in the database with a timestamp > limit
    def post_is_in_db_with_old_timestamp(self, title):
        for key in self.posts.keys():
            # print("key = '{}', post = '{}'".format(key, self.posts[key]))
            if title == self.posts[key].title:
                ts_as_string = str(key)
                ts = int(ts_as_string)
                if self.current_timestamp - ts > self.limit:
                    return True
        return False

    def sort_posts(self):
        #
        # get the feed data from the url
        #
        self.feed = feedparser.parse(self.url)
        print("got {} entries from {}".format(len(self.feed.entries), self.url))

        #
        # figure out which posts to print
        #
        self.posts_to_print = []
        self.posts_to_skip = []

        # print("number of entries = {}".format(len(self.feed.entries)))
        now = datetime.now()
        for entry in self.feed.entries:
            # print("keys = {}".format(entry.keys()))
            # if it is not today's news, skip it
            if "published_parsed" in entry.keys():
                pparsed = entry["published_parsed"]
                if self.verbose:
                    print("pparsed = {}".format(pparsed))
                if not now.day == pparsed.tm_mday:
                    if self.verbose:
                        print("discarding yesterday's news")
                    continue
            # if entry is already in the database, skip it
            # TODO check the time
            title = entry.title
            # print("checking title '{}'".format(title))
            if self.post_is_in_db_with_old_timestamp(title):
                self.posts_to_skip.append(title)
            else:
                # print("adding {} to db".format(title))
                self.posts_to_print.append(title)
        self.add_posts_to_db()

    def add_posts_to_db(self):
        #
        # add all the posts we're going to print to the database with the current timestamp
        # (but only if they're not already in there)
        #
        for title in self.posts_to_print:
            if not self.post_is_in_db(title):
                self.posts[str(self.current_timestamp)] = title


class panelApp(SampleBase):

    """
    Initialize
    """

    def __init__(self, *args, **kwargs):
        super(panelApp, self).__init__(*args, **kwargs)
        self.rssApp = rss()
        self.iconSize = 64

    """
    get the curent weather data, if it is unavailable then just use what we have
    from the last successful call
    """

    def getWeather(self):
        print(
            "getting weather from {}?{} at {}".format(
                self.weatherUri, self.params, datetime.now().strftime("%c")
            )
        )
        try:
            r = requests.get(url=self.weatherUri, params=self.params)
        except:
            e = sys.exc_info()[0]
            print("Exception found while getting weather data: " + str(e))
            return
        data = r.json()
        self.parseData(data)

    """
    parse the Json returned from getWeather()
    """

    def parseData(self, data):
        # Extract current weather data
        current = data["current"] 
        # Extract sunrise, sunset, temperature, cloudiness, and wind data
        self.sunrise = current["sunrise"]
        self.sunset = current["sunset"]
        self.temperatureNow = current["temp"]
        self.clouds = current["clouds"]
        self.windSpeed = current["wind_speed"]
        self.windDir = self.degToCompass(int(current["wind_deg"]))
        self.humidity = current["humidity"]

        # Access the first item in the 'weather' array
        weather_info = current["weather"][0]
    
        # Extract the main weather condition (e.g., 'Clear', 'Clouds')
        self.weatherMain = weather_info["main"]  # This will be something like 'Clear', 'Clouds', etc.
    
        # Handling possible weather alerts
        alerts = []
        if "alerts" in data:  # Safely check if alerts exist in the data
            alerts = data["alerts"]

        # Extract weather icon ID and load the associated icon
        iconId = current["weather"][0]["icon"]
        self.loadAndSaveIcon(iconId)
        filename = "./icons/" + iconId + ".png"
        self.weatherIcon = Image.open(filename)
  
        # Delete old alerts on every call
        for alert in alerts:
            # Ensure the description is available before using it
            if "description" in alert:
                description = alert["description"].replace("\n", " ")
                if description not in self.alertArray:
                    self.alertArray.append(description)
                else:
                    self.alertArray.remove(description)

        # Extract daily forecast data (min/max temperature and main weather)
        self.daily = data["daily"]
        temperatures = self.daily[0]["temp"]
        self.minTemp = temperatures["min"]
        self.maxTemp = temperatures["max"]
        # Get the main weather information for the first day
        main_weather = self.daily[0]["weather"][0]  # The 'weather' array contains information about the weather conditions
        self.weatherDescription = main_weather["description"]  # E.g., "clear sky"
        self.dailyWeatherMain = main_weather["main"]  # E.g., "Clear", "Rain", etc.

    def degToCompass(self, num):
        val = int((num / 22.5) + 0.5)
        arr = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        return arr[(val % 16)]

    """
    Image handlers
    """

    def trimImage(self, image):
        image_data = np.asarray(image)
        image_data_bw = image_data.max(axis=2)
        non_empty_columns = np.where(image_data_bw.max(axis=0) > 0)[0]
        non_empty_rows = np.where(image_data_bw.max(axis=1) > 0)[0]
        cropBox = (
            min(non_empty_rows),
            max(non_empty_rows),
            min(non_empty_columns),
            max(non_empty_columns),
        )
        image_data_new = image_data[
            cropBox[0] : cropBox[1] + 1, cropBox[2] : cropBox[3] + 1, :
        ]
        new_image = Image.fromarray(image_data_new)
        return new_image

    """
    load and save the png to disk iffi it is not already saved
    """

    def loadAndSaveIcon(self, iconId):
        url = "http://openweathermap.org/img/w/" + iconId + ".png"
        filename = "./icons/" + iconId + ".png"
        if not path.exists(filename):
            r = requests.get(url, allow_redirects=True)
            imgfile = io.BytesIO(r.content)
            img = Image.open(imgfile)
            rgba = np.array(img)
            rgba[rgba[..., -1] == 0] = [0, 0, 0, 0]
            im = Image.fromarray(rgba)
            im = self.trimImage(im)
            im.thumbnail((36, 36))
            if self.verbose:
                print("Creating icon file: {}".format(filename))
            im.save(filename)
        else:
            im = Image.open(filename)
        return im

    def drawImage(self, imageFilename):
        image = Image.open(imageFilename)
        image.thumbnail((self.iconSize, self.iconSize), Image.ANTIALIAS)
        self.matrix.SetImage(image.convert("RGB"), self.xpos, 30)

    def drawScreen(self):
        alertNo = 0
        rssNo = 0
        lineHeight = 10

        self.rssApp.sort_posts()
        self.getWeather()

        ypos = self.offscreen_canvas.height - self.lineSpacing
        self.xpos = self.offscreen_canvas.width

        loopCounter = 0
        timeOut = self.rssTimeOut
        # timeOut = 8 * 60 * 2 # debugging only
        tensec = 8 * 10

        dayIndex = 0
        dayName = "Today"

        # initialize the weather info iffi the http request has completed
        #
        if not self.weatherIcon == None:
            temperatures = self.daily[0]["temp"]
            minTemp = temperatures["min"]
            maxTemp = temperatures["max"]
            iconId = self.daily[0]["weather"][0]["icon"]
            self.loadAndSaveIcon(iconId)
            filename = "./icons/" + iconId + ".png"
            weatherIcon = Image.open(filename)
            feedSwitch = False

        while True:
            # use this to time the loop and set the intervals for getWeather() and dayIndex
            # on a Pi Zero W it's 8 loops/sec
            # print("loopCounter = {} at {}".format(loopCounter, datetime.now().strftime("%c")))
            now = datetime.now()
            timeNow = now.strftime("%I:%M")
            dateNow = now.strftime("%a %b %-d %Y")
            self.offscreen_canvas.Clear()

            # init the weather info iffi the http request has completed
            #
            if not self.weatherIcon == None:
                # increment the dayIndex every minute
                if loopCounter % tensec == 0:
                    dayIndex = (dayIndex + 1) % 8
                    if dayIndex == 0:
                        dayName = "Today"
                    else:
                        dayName = time.strftime(
                            "%a", time.localtime(self.daily[dayIndex]["dt"])
                        )
                    temperatures = self.daily[dayIndex]["temp"]
                    minTemp = temperatures["min"]
                    maxTemp = temperatures["max"]
                    iconId = self.daily[dayIndex]["weather"][0]["icon"]
                    weatherIcon = self.loadAndSaveIcon(iconId)
                    self.dailyWeatherMain = self.daily[dayIndex]["weather"][0]["main"]

            # draw the date
            graphics.DrawText(
                self.offscreen_canvas,
                self.font,
                12,
                lineHeight,
                graphics.Color(51, 153, 255),
                dateNow,
            )
            # draw the time
            graphics.DrawText(
                self.offscreen_canvas,
                self.fontB,
                46,
                2 * lineHeight + 1,
                graphics.Color(0, 215, 100),
                timeNow,
            )
            # draw the alert text or the RSS feed if there are no alerts
            # if feedSwitch is True - draw alerts, else draw RSS
            if feedSwitch:
                if len(self.alertArray) > 0:
                    slen3 = graphics.DrawText(
                        self.offscreen_canvas,
                        self.fontMed,
                        self.xpos,
                        ypos,
                        graphics.Color(255, 20, 20),
                        self.alertArray[alertNo],
                    )
            else:
                # print("printing post[{}] = '{}'".format(rssNo, self.rssApp.posts_to_print[rssNo]))
                if len(self.rssApp.posts_to_print) > 0:
                    slen3 = graphics.DrawText(
                        self.offscreen_canvas,
                        self.fontMed,
                        self.xpos,
                        ypos,
                        graphics.Color(21, 128, 6),
                        self.rssApp.posts_to_print[rssNo],
                    )

            # draw the weather info iffi the http request has completed
            if not self.weatherIcon == None:
                self.offscreen_canvas.SetImage(
                    weatherIcon.convert("RGB"),
                    48,
                    2 * lineHeight + self.lineSpacing + 1,
                )

                # draw the label
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontSmall,
                    3,
                    2 * lineHeight + self.lineSpacing,
                    graphics.Color(255, 255, 255),
                    "Now:",
                )
                def get_temperature_color(temp, min_temp, max_temp):
                # Map the temperature to a color in the range -20°F to 120°F, with yellow in the middle.
    
                    if temp <= -20:
                        return graphics.Color(0, 0, 255)  # Blue for cold
                    elif temp >= 120:
                        return graphics.Color(255, 0, 0)  # Red for hot
                    elif temp <= 70:
                        # From -20°F to 60°F, color transitions from blue to green
                        normalized_temp = (temp + 20) / 90  # Normalize between 0 and 1 for -20°F to 60°F
                        red = 0
                        green = int(255 * normalized_temp)
                        blue = int(255 * (1 - normalized_temp))
                        return graphics.Color(red, green, blue)
                    else:
                        # From 70°F to 120°F, color transitions from green to red
                        normalized_temp = (temp - 70) / 50  # Normalize between 0 and 1 for 60°F to 120°F
                        red = int(255 * normalized_temp)
                        green = int(255 * (1 - normalized_temp))
                        blue = 0
                        return graphics.Color(red, green, blue)

                # For the current temperature:
                current_color = get_temperature_color(self.temperatureNow, minTemp, maxTemp)
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    3,
                    3 * lineHeight + self.lineSpacing,
                    current_color,
                    str(int(self.temperatureNow)) + u"\u00b0" + "F",
                )

                # For the minimum temperature:
                min_temp_color = get_temperature_color(minTemp, minTemp, maxTemp)
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    50 + 36,
                    3 * lineHeight + self.lineSpacing,
                    min_temp_color,
                    str(int(minTemp)),
                )
                # Draw the "/" symbol in a fixed color (e.g., black or white)
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    50 + 35 + len(str(int(minTemp))) * self.fontMed.CharacterWidth(0),  # Adjust position after the min temperature
                    3 * lineHeight + self.lineSpacing,
                    graphics.Color(255, 255, 255),  # White color for the "/"
                    "/",
                )

                # For the maximum temperature:
                max_temp_color = get_temperature_color(maxTemp, minTemp, maxTemp)
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    50 + 53,
                    3 * lineHeight + self.lineSpacing,
                    max_temp_color,
                    str(int(maxTemp)),
                )
                
                # Draw the unit symbol "°F" for the max temperature in a fixed color (e.g., black or white)
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    50 + 59 + len(str(int(minTemp))) * self.fontMed.CharacterWidth(10) + 10 + len(str(int(maxTemp))) * self.fontMed.CharacterWidth(10),  # Adjust position after max temperature
                    3 * lineHeight + self.lineSpacing,
                    graphics.Color(255, 255, 255),  # White color for the degree symbol and "F"
                    u"\u00b0" + "F",  # Degree symbol and "F"
                )
                
                # draw the daily weather outlook
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    50 + 36,
                    4 * lineHeight + self.lineSpacing,
                    graphics.Color(0, 128, 255),
                    str(self.dailyWeatherMain),
                )
                
                # draw the current condition
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    2,
                    4 * lineHeight + self.lineSpacing,
                    graphics.Color(0, 128, 255),
                    str(self.weatherMain),
                )
                # draw the wind speed and direction
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontMed,
                    15,
                    5 * lineHeight + 3,
                    graphics.Color(0, 255, 255),
                    str(int(self.windSpeed)) + "mph from the " + self.windDir,
                )

                # draw the label
                graphics.DrawText(
                    self.offscreen_canvas,
                    self.fontSmall,
                    50 + 46,
                    2 * lineHeight + self.lineSpacing,
                    graphics.Color(255, 255, 255),
                    dayName + ":",
                )

            # move the scroll text 1 pixel
            self.xpos = self.xpos - 1

            if len(self.alertArray) > 0 or len(self.rssApp.posts_to_print) > 0:
                if (self.xpos + slen3) < 0:
                    # since fetching the weather/RSS feed can change
                    # the scrolling text, only do it when there is
                    # nothing to scroll

                    # get the weather and RSS info every timeOut passes through the loop
                    # if(loopCounter % 20) == 0:
                    # print("loopCounter = {}, timeOut = {}".format(loopCounter, timeOut))
                    if loopCounter > timeOut:
                        # change the scrolling display data
                        feedSwitch = not feedSwitch
                        if feedSwitch:
                            self.getWeather()
                            timeOut = self.weatherTimeOut
                        else:
                            timeOut = self.rssTimeOut
                            # if there is more than 1 feed then rotate feeds
                            feedArrayLen = len(self.feedArray)
                            if feedArrayLen > 1:
                                self.feedNo += 1
                            if self.feedNo >= feedArrayLen:
                                self.feedNo = 0
                            self.rssApp.url = self.feedArray[self.feedNo]
                            self.rssApp.sort_posts()

                        # reset the loop counter
                        loopCounter = 0

                    # Start scrolling the next alert or RSS entry
                    self.xpos = self.offscreen_canvas.width
                    if feedSwitch:
                        alertNo = alertNo + 1
                        if alertNo >= len(self.alertArray):
                            alertNo = 0
                    else:
                        rssNo = rssNo + 1
                        # print("rssNo = {}, length = {}".format(rssNo, len(self.rssApp.posts_to_print)))
                        if rssNo >= len(self.rssApp.posts_to_print):
                            rssNo = 0

            time.sleep(0.04)
            self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)
            loopCounter = loopCounter + 1

    """
    error handler for options, if second arg is '', the the whole section is missing
    or invalid
    """

    def handleOptionsError(self, section, key):
        if key == "":
            print(
                "The configuration's section '"
                + section
                + "' is missing or contains invalid entries"
            )
        else:
            print(
                "The key '"
                + key
                + "' in section '"
                + section
                + "' is missing or invalid"
            )
        print("Please consult the README.md file for more information")
        sys.exit(-1)

    def setup(self):
        config = configparser.ConfigParser()
        config.read("weatherPanel.cfg")

        #
        # LED section
        #
        options = RGBMatrixOptions()
        if "LED" in config:
            ledOptions = config["LED"]
            options.cols = int(ledOptions.get("cols", 64))
            options.rows = int(ledOptions.get("rows", 32))
            options.chain_length = int(ledOptions.get("chain_length", 4))
            options.brightness = int(ledOptions.get("brightness", 100))
            options.gpio_slowdown = int(ledOptions.get("gpio_slowdown", 1))
            options.pwm_bits = int(ledOptions.get("pwm_bits", 11))
            options.pwm_dither_bits = int(ledOptions.get("pwm_dither_bits", 0))
            options.pwm_lsb_nanoseconds = int(ledOptions.get("pwm_lsb_nanoseconds", 130))
            options.parallel = int(ledOptions.get("parallel", 1))
            options.show_refresh_rate = bool(ledOptions.get("True", True))
            options.hardware_mapping = ledOptions.get(
                "hardware_mapping", "adafruit-hat-pwm"
            )
#            options.pixel_mapper_config = ledOptions.get(
#                "pixel_mapper_config", "U-mapper"
#            )
            self.matrix = RGBMatrix(options=options)
        else:
            self.handleOptionsError("LED", "")

        #
        # WEATHER section
        #
        if "WEATHER" in config:
            weatherOptions = config["WEATHER"]
            if "lat" in weatherOptions:
                lat = weatherOptions.get("lat")
            else:
                self.handleOptionsError("WEATHER", "lat")
            if "lon" in weatherOptions:
                lon = weatherOptions.get("lon")
            else:
                self.handleOptionsError("WEATHER", "lon")
            if "units" in weatherOptions:
                units = weatherOptions.get("units", "imperial")
            if "appid" in weatherOptions:
                appid = weatherOptions["appid"]
            else:
                self.handleOptionsError("WEATHER", "appid")
        else:
            self.handleOptionsError("WEATHER", "")
        self.weatherUri = "https://api.openweathermap.org/data/3.0/onecall"
        self.params = (
            "lat=" + lat + "&lon=" + lon + "&appid=" + appid + "&units=" + units
        )

        #
        # RSS section
        #
        self.feedArray = []
        if "RSS" in config:
            rssOptions = config["RSS"]
            if "feed" in rssOptions:
                self.feedArray = rssOptions.get("feed", "").split("\n")
                self.rssApp.url = self.feedArray[0]

        #
        # MISC section
        #
        if "MISC" in config:
            miscOptions = config["MISC"]
            self.weatherTimeOut = int(miscOptions.get("weatherTimeOut", 8 * 60 * 10))
            self.rssTimeOut = int(miscOptions.get("rssTimeOut", 8 * 60 * 30))
            self.rssApp.verbose = self.verbose = miscOptions.get("verbose", False)
        else:
            self.weatherTimeOut = 8 * 60 * 10
            self.rssTimeOut = 8 * 60 * 30
            self.rssApp.verbose = self.verbose = False

        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.font = graphics.Font()
        self.font.LoadFont("./fonts/7x13.bdf")
        self.fontB = graphics.Font()
        self.fontB.LoadFont("./fonts/7x13B.bdf")
        self.fontMed = graphics.Font()
        self.fontMed.LoadFont("./fonts/6x9.bdf")
        self.fontSmall = graphics.Font()
        self.fontSmall.LoadFont("./fonts/5x8.bdf")
        self.textColor = graphics.Color(0, 0, 128)
        self.xpos = 0
        self.lineSpacing = 1

        self.degreeSign = "\u00B0"

        self.alertArray = []
        self.weatherIcon = None
        self.feedNo = 0


def handler(signum, frame):
    global app

    app.offscreen_canvas.Clear()
    sys.exit(0)


def main():
    global app

    app = panelApp()
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    app.setup()
    app.drawScreen()


# Main function
if __name__ == "__main__":
    main()
