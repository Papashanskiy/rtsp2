#!/usr/bin/env python
import os
import json
import subprocess
import time
import glob
import sys
import cv2 as cv
import random
import re
import datetime
import logging

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def camera_info(fun, input_str: str) -> tuple:
    """
    This function counts function execution time
    """
    t_start = time.time()
    if input_str and type(input_str) != str:
        logging.critical("Parameter [rtsp] must be a str type!")
        sys.exit()
    result = fun(input_str)
    t_end = time.time()
    delta_time = t_end - t_start
    return result, delta_time


def name_timestamp() -> str:
    """
    This function generates unique name for mp4 file
    """
    name = 'file{}'.format(time.strftime("%Y%m%d%H%M%S")) + str(random.randint(10000, 99999))
    return name


MP4_FILE_NAME = name_timestamp() + '.mp4'


def cleaner(file_name: str):
    """
    Cleaner function. It remove one extra file .mp4
    """
    files = os.path.join(BASE_DIR, file_name)
    if files:
        try:
            os.remove(files)
        except Exception as e:
            logging.critical("Program can`t remove file {} - {}".format(os.path.join(BASE_DIR, file_name), e))


def full_cleaner() -> None:
    """
    Cleaner function. It remove all extra files .mp4
    """
    try:
        if glob.glob('*.mp4'):
            for i in glob.glob('*.mp4'):
                stat = os.stat(os.path.join(BASE_DIR, i))
                if datetime.datetime.fromtimestamp(stat.st_mtime) < datetime.datetime.now() - datetime.timedelta(
                        seconds=60):
                    os.remove(os.path.join(BASE_DIR, i))
    except Exception as e:
        logging.error(e)


def get_info(rtsp: str) -> dict:
    """
    This function takes rtsp, then copies 27 frames from given rtsp stream to mp4 file, get the info we need using
    FFProbe and OpenCV. Return dict with info about given rtsp stream.
    :return: dict
    """
    FNULL = open(os.devnull, 'w')
    mp4_file = MP4_FILE_NAME

    # Coping 26 frames from rtsp
    request = "ffmpeg -rtsp_transport tcp -i {} -c copy -map 0 -frames 27 -an -dn {}".format(rtsp, mp4_file)
    try:
        output = subprocess.Popen([request], stdout=FNULL, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logging.critical("Something going wrong when program tried to execute the request {}".format(request))
        if e.output.startwith('error: {'):
            error = json.loads(e.output[7:])
            logging.critical("{} - {}".format(error['code'], error['message']))
        sys.exit()

    # Waiting until file appears and then get info about it
    # If this piece of code spins to long program stop working
    t_start = time.time()
    t_limit = 20
    while True:
        time.sleep(0.1)
        t_current = time.time()
        if glob.glob(mp4_file):
            # Get bitrate and resolution from video including FFMpeg and FFProbe
            request = "ffprobe -v error -select_streams v:0 -show_entries stream=width,height,bit_rate,r_frame_rate,duration -of default=noprint_wrappers=1 -print_format json {}".format(
                mp4_file)
            try:
                proc = subprocess.Popen([request], stdout=subprocess.PIPE, shell=True)
                output, err = proc.communicate()
                data = json.loads(output)
            except subprocess.CalledProcessError as e:
                logging.critical("Something going wrong when program tried to execute the request {}".format(request))
                if e.output.startwith('error: {'):
                    error = json.loads(e.output[7:])
                    logging.critical("{} - {}".format(error['code'], error['message']))
                sys.exit()

            #  Get fps from video including OpenCV lib
            video = cv.VideoCapture(mp4_file)
            fps = video.get(cv.CAP_PROP_FPS)
            video.release()
            break
        elif t_current - t_start >= t_limit:
            logging.critical("Something going wrong when program tried to get needed {} file.".format(mp4_file))
            sys.exit()

    # Removing mp4 file, coz we no longer need it
    try:
        if glob.glob(MP4_FILE_NAME):
            os.remove(mp4_file)
    except Exception as e:
        logging.error("Program Can`t remove file {}".format(os.path.join(BASE_DIR, MP4_FILE_NAME)))

    # Generating the response dict
    try:
        response = {
            'fps': round(fps),  # round(26 / float(data['streams'][0]['duration']))
            'resolution': str(str(data['streams'][0]['width']) + 'x' + str(data['streams'][0]['height'])),
            'bitrate': data['streams'][0]['bit_rate'],
        }
    except Exception as e:
        logging.critical(
            "Something going wrong when program tried to return info about fps, bitrate or resolution. {} - {}".format(
                e.__class__.__name__, e))
        sys.exit()

    return response


def check_rtsp(rtsp: str) -> bool:
    """
    This function check given rtsp and if something wrong it return False else it return True if all is alright.
    :return: bool
    """
    request = "ffprobe -v error -select_streams v:0 -of default=noprint_wrappers=1 {}".format(rtsp)
    try:
        proc = subprocess.Popen([request], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            if proc.wait(15) == 1:
                pass
        except subprocess.TimeoutExpired as e:
            logging.critical("Response time too long. Possibly wrong ip.")
            sys.exit()
        out, err = proc.communicate()
        err = err.decode('utf-8') if type(err) != str else ''
        if err != '':  # If an error is present
            if bool(re.search(r"\bInvalid data found\b", err)) or \
                    bool(re.search(r"\bNo route to host\b", err)) or \
                    bool(re.search(r"\bName or service not\b", err)):  # If it`s error with wrong ip
                logging.critical("Wrong ip.")
                return False
            if bool(re.search(r"\b401 Unauthorized\b", err)):  # If it`s error with wrong auth
                logging.critical("Authorization failed!")
                return False
            if bool(re.search(r"\bConnection refused\b", err)):  # If it`s error with wrong port
                logging.critical("Wrong port.")
                return False
            if bool(re.search(r"\bh264 @ \b", err)):  # If it`s not a fatal error
                return True
            print(err.encode())
            logging.critical("Something going wrong.")
            return False
        return True
    except subprocess.CalledProcessError as e:
        if e.output.startwith('error: {'):
            error = json.loads(e.output[7:])
            logging.critical("{} - {}".format(error['code'], error['message']))
            return False


def main():
    """
    Main function. It processing the received arguments and runs a function
    """
    parameters = ['fps', 'resolution', 'bitrate']
    if len(sys.argv) >= 4:
        if len(sys.argv) == 5:
            if sys.argv[4] == '-l' or sys.argv[4] == '--log':
                logging.basicConfig(
                    filename=os.path.join(os.getcwd(), 'logfile'),
                    format='%(asctime)s - %(levelname)s - {} - %(message)s'.format(sys.argv[2]), level=logging.ERROR
                )
        if not check_rtsp(sys.argv[2]):  # if user set wrong rtsp == False -> Error
            sys.exit()
        if sys.argv[3] not in parameters:
            logging.critical("Parameter must be 'fps', 'resolution' or 'bitrate'")
            sys.exit()
        data = camera_info(get_info, input_str=sys.argv[2])
        print(data[0][sys.argv[3]])
    else:
        logging.critical("Incorrect program input: ./check_cam [type] [rtsp] [param] [-l/]")
        cleaner(MP4_FILE_NAME)
        sys.exit()

    full_cleaner()


if __name__ == '__main__':
    main()
