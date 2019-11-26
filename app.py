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
import click


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ERROR_TEXT = " Error!\n {}\n" \
             " ./check_cum.py ['name of type camera': str] ['rtsp': str] ['param': str]\n\n" \
             " Examples:\n" \
             " ./check_cam.py 'ПВН' 'rtsp://admin:region18@192.168.30.25:554/av0_0' 'resolution'\n" \
             " ./check_cam.py ПВН rtsp://admin:region18@192.168.30.25:554/av0_0 resolution"

def camera_info(fun, input_str: str) -> tuple:
    """
    This function counts function execution time
    """
    t_start = time.time()
    if input_str and type(input_str) != str:
        print("Option -i must be a str type!")
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
            print('Error!\nProgram Can`t remove file {} \nin directory {}'
                  '\nException: '
                  '\n'.format(file_name, BASE_DIR), e.__class__.__name__, e)


def full_cleaner() -> None:
    """
    Cleaner function. It remove all extra files .mp4
    """
    try:
        if glob.glob('*.mp4'):
            for i in glob.glob('*.mp4'):
                stat = os.stat(os.path.join(BASE_DIR, i))
                if datetime.datetime.fromtimestamp(stat.st_mtime) < datetime.datetime.now() - datetime.timedelta(seconds=30):
                    os.remove(os.path.join(BASE_DIR, i))
    except Exception as e:
        print(e)

def get_info(rtsp: str) -> dict:
    """
    This function takes rtsp, then copies 27 frames from given rtsp stream to mp4 file, get the info we need using
    FFProbe and OpenCV. Return dict with info about given rtsp stream.
    :return:
    """
    FNULL = open(os.devnull, 'w')
    mp4_file = MP4_FILE_NAME

    # Coping 26 frames from rtsp
    request = "ffmpeg -rtsp_transport tcp -i {} -c copy -map 0 -frames 27 -an -dn {}".format(rtsp, mp4_file)
    try:
        output = subprocess.Popen([request], stdout=FNULL, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print('Error!\nSomething going wrong when program tried to execute the request \n{}'
              '\nException: '
              '\n'.format(request))
        if e.output.startwith('error: {'):
            error = json.loads(e.output[7:])
            print(error['code'])
            print(error['message'])
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
            request = "ffprobe -v error -select_streams v:0 -show_entries stream=width,height,bit_rate,r_frame_rate,duration -of default=noprint_wrappers=1 -print_format json {}".format(mp4_file)
            try:
                proc = subprocess.Popen([request], stdout=subprocess.PIPE, shell=True)
                output, err = proc.communicate()
                data = json.loads(output)
            except subprocess.CalledProcessError as e:
                print('Error!\nSomething going wrong when program tried to execute the request \n{}'
                      '\nException: '
                      '\n'.format(request))
                if e.output.startwith('error: {'):
                    error = json.loads(e.output[7:])
                    print(error['code'])
                    print(error['message'])
                sys.exit()

            #  Get fps from video including OpenCV lib
            video = cv.VideoCapture(mp4_file)
            fps = video.get(cv.CAP_PROP_FPS)
            video.release()
            break
        elif t_current - t_start >= t_limit:
            print("Error!\nSomething going wrong when program tried to get needed {} file.".format(mp4_file))
            sys.exit()

    # Removing mp4 file, coz we no longer need it
    try:
        if glob.glob(MP4_FILE_NAME):
            os.remove(mp4_file)
    except Exception as e:
        print('Error!\nProgram Can`t remove file {} \nin directory {}'
              '\nException: '
              '\n'.format(MP4_FILE_NAME, BASE_DIR), e.__class__.__name__, e)

    # Generating the response dict
    try:
        response = {
            'fps': round(fps), #   round(26 / float(data['streams'][0]['duration']))
            'resolution': str(str(data['streams'][0]['width']) + 'x' + str(data['streams'][0]['height'])),
            'bitrate': data['streams'][0]['bit_rate'],
        }
    except Exception as e:
        print("Error!\nSomething going wrong when program tried to return info about fps, bitrate or resolution.\n",
              e.__class__.__name__, e)
        sys.exit()

    return response


def check_rtsp(rtsp: str) -> bool:
    request = "ffprobe -v error -select_streams v:0 -of default=noprint_wrappers=1 {}".format(rtsp)
    try:
        proc = subprocess.Popen([request], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        err = err.decode('utf-8') if type(err) != str else ''
        if err != '':   # If an error is present
            if bool(re.search(r"\bInvalid data found\b", err)):    # If it`s error with wrong ip
                print(err, end='')
                print("Error!\nProgram can`t connect to this rtsp.\nCheck the correctness of the entered.\nWrong ip.")
                return False
            if bool(re.search(r"\b401 Unauthorized\b", err)):  # If it`s error with wrong auth
                print(err, end='')
                print("Error!\nAuthorization failed!")
                return False
            if bool(re.search(r"\bConnection refused\b", err)):    # If it`s error with wrong port
                print(err, end='')
                print("Error!\nWrong port.")
                return False
            if bool(re.search(r"\bh264 @ \b", err)): # If it`s not a fatal error
                return True
            print(err, end='')
            print("Error!\nSomething going wrong.")
            return False
        return True
    except subprocess.CalledProcessError as e:
        if e.output.startwith('error: {'):
            error = json.loads(e.output[7:])
            print(error['code'])
            print(error['message'])
            return False


@click.command()
@click.option('--log', '-l', is_flag=True)
def main(log):
    """
    Main function. It processing the received arguments and runs a function
    """
    parameters = ['fps', 'resolution', 'bitrate']
    if len(sys.argv) == 4:
        if not check_rtsp(sys.argv[2]): # if check_rtsp == False -> Error
            sys.exit()
        if sys.argv[3] not in parameters:
            print(ERROR_TEXT.format("Parameter must be 'fps', 'resolution' or 'bitrate'"))
            sys.exit()
        data = camera_info(get_info, input_str=sys.argv[2])
        print(data[0][sys.argv[3]])
        # print("Total time: ", data[1])    # Print total time
    else:
        print(ERROR_TEXT.format("Input values should look like this:"))
        cleaner(MP4_FILE_NAME)
        sys.exit()

    full_cleaner()


if __name__ == '__main__':
    main()
