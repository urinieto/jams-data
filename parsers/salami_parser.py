#!/usr/bin/env python
"""
This script parses the SALAMI v2.0 dataset into the JAMS format.

Usage example:
    ./salami_parser.py salami-data-public/ OutputSalamiJAMS
"""

import argparse
import csv
from joblib import Parallel, delayed
import logging
import numpy as np
import os
import time

import jams

__author__ = "Oriol Nieto"
__copyright__ = "Copyright 2016, Music and Audio Research Lab (MARL)"
__license__ = "MIT"
__version__ = "1.2"
__email__ = "oriol@nyu.edu"

SALAMI_VERSION = "2.0"
SALAMI_CORPUS_NAME = "SALAMI"
SALAMI_ANN_TOOL = "Sonic Visualiser"
SALAMI_CURATOR = "Jordan Smith"
SALAMI_EMAIL = "jblsmith@gmail.com"

# Mapping of the labels to the actual labels allowed by the SALAMI guidelines
labels_map = {
    "a'/a''": "no_function",
    "b/c'": "no_function",
    "bagpipes": "instrumental",
    "banjo": "instrumental",
    "code": "coda",
    "dialog": "spoken",
    "female": "voice_female",
    "first": "main theme",
    "guitar": "instrumental",
    "hammond": "instrumental",
    "main_theme": "main theme",
    "male": "voice_male",
    "muted": "fade-out",
    "organ": "instrumental",
    "out": "outro",
    "piano": "instrumental",
    "recap": "recapitulation",
    "secondary_theme": "secondary theme",
    "spoken_voice": "spoken",
    "stage_speaking": "spoken",
    "steel": "instrumental",
    "tag": "head",
    "trumpet": "instrumental",
    "third": "third theme",
    "violin": "instrumental",
    "vocalizations": "voice",
    "vocals": "voice",
    "w/dialog": "spoken"
}


def fix_label(label):
    """Fixes the given label to comply the SALAMI guidelines and JAMS
    namespace."""
    label = label.lower()
    return labels_map.get(label, label)


def parse_annotation(jam, ann_file, annotation_id, level, metadata):
    """Parses one annotation for the given level

    Parameters
    ----------
    jam: object
        The top-level JAMS object.
    ann_file: str
        Path to the annotation file (raw version, not previously parsed).
    annotation_id: int
        Whether to use the first or the second annotation.
    level: str
        Level of annotation.
    metadata: list
        List containing the information of the CSV file for the current track.
    """
    namespace_dict = {
        "function": "segment_salami_function",
        "large_scale": "segment_salami_upper",
        "small_scale": "segment_salami_lower"
    }
    # Open file
    try:
        f = open(ann_file, "r")
    except IOError:
        logging.warning("Annotation missing in %s", ann_file)
        return

    # Annotation Metadata
    curator = jams.Curator(name=SALAMI_CURATOR, email=SALAMI_EMAIL)
    annotator = {
        "name": metadata[annotation_id + 1],
        "submission_date": metadata[annotation_id + 15]
    }
    ann_meta = jams.AnnotationMetadata(curator=curator,
                                       version=SALAMI_VERSION,
                                       corpus=SALAMI_CORPUS_NAME,
                                       annotator=annotator,
                                       data_source=metadata[1],
                                       annotation_tools=SALAMI_ANN_TOOL)

    # Create Annotation
    annot = jams.Annotation(namespace=namespace_dict[level],
                            annotation_metadata=ann_meta)

    # Actual Data
    lines = f.readlines()
    for i, line in enumerate(lines[:-1]):
        start_time, label = line.strip("\n").split("\t")
        end_time = lines[i + 1].split("\t")[0]
        start_time = float(start_time)
        end_time = float(end_time)
        dur = end_time - start_time
        if start_time - end_time == 0:
            continue

        if level == "function":
            label = fix_label(label)

        annot.data.add_observation(time=start_time, duration=dur, value=label)
    f.close()

    # Add annotation to the jams
    jam.annotations.append(annot)


def fill_global_metadata(jam, metadata, dur):
    """Fills the global metada into the JAMS jam."""
    meta = jams.FileMetadata(title=metadata[7],
                             artist=metadata[8],
                             duration=dur,
                             jams_version=jams.version.version)
    jam.file_metadata = meta


def create_annotations(jam, ann_file, annotation_id, metadata):
    """Fills the JAMS annot annotation given a path to the original
    SALAMI annotations. The variable "annotator" let's you choose which
    SALAMI annotation to use.

    Parameters
    ----------
    jam: object
        The top-level JAMS object.
    path: str
        Patht to the file containing the annotations.
    annotation_id: int
        Identifier of the annotator (1, 2, or 3)
    metadata: list
        List containing the information of the CSV file for the current track.
    """
    # Parse all level annotations
    levels = ["function", "large_scale", "small_scale"]
    [parse_annotation(jam, ann_file, annotation_id, level, metadata)
        for level in levels]


def get_duration(jam):
    """Obtains the duration from the jams annotations.

    Parameters
    ----------
    jam : object
        JAMS object with at least one annotation.

    Returns
    -------
    dur : float
        Duration of the file, by taking the max last boundary of all
        annotations (in seconds).
    """
    durs = []
    for annotation in jam.annotations:
        durs.append(annotation.data["time"].iloc[-1].total_seconds() +
                    annotation.data["duration"].iloc[-1].total_seconds())
    return np.max(durs)


def create_JAMS(in_dir, metadata, out_file):
    """Creates a JAMS file given the path to a SALAMI track.

    Parameters
    ----------
    in_dir : str
        Path to the input directory
    metadata : str
        Metadata read from the CSV file
    out_file : str
        Output JAMS file
    """
    path = os.path.join(in_dir, "annotations", metadata[0], )

    # Sanity check
    if not os.path.exists(path):
        logging.warning("Path not found %s", path)
        return

    # New JAMS and annotation
    jam = jams.JAMS()

    # Create Annotations if they exist
    # Maximum 3 annotations per file
    for annotation_id in range(1, 4):
        ann_file = os.path.join(path, "textfile" + str(annotation_id) + ".txt")
        if os.path.isfile(ann_file):
            create_annotations(jam, ann_file, annotation_id, metadata)

    # Get the duration from the annotations
    dur = get_duration(jam)

    # Global file metadata
    fill_global_metadata(jam, metadata, dur)

    # Save JAMS
    jam.save(out_file)


def process_one(metadata, in_dir, out_dir):
    """Processes one track given its metadata."""
    if metadata[0] == "SONG_ID":
        return

    # Create a JAMS file for this track
    logging.info("Parsing file %s..." % metadata[0])
    create_JAMS(in_dir, metadata,
                os.path.join(out_dir, os.path.basename(metadata[0]) + ".jams"))


def process(in_dir, out_dir, n_jobs):
    """Converts the original SALAMI files into the JAMS format, and saves
    them in the out_dir folder."""

    # Check if output folder and create it if needed:
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # Open CSV with metadata and parse
    with open(os.path.join(in_dir, "metadata", "metadata.csv")) as fh:
        csv_reader = csv.reader(fh)
        Parallel(n_jobs=n_jobs)(delayed(process_one)(
            metadata, in_dir, out_dir) for metadata in list(csv_reader))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Converts the SALAMI dataset to the JAMS format",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("in_dir",
                        action="store",
                        help="SALAMI main folder")
    parser.add_argument("out_dir",
                        action="store",
                        help="Output JAMS folder")
    parser.add_argument("-j",
                        dest="n_jobs",
                        action="store",
                        type=int,
                        default=2,
                        help="Number of CPUs to run in parallel.")
    args = parser.parse_args()
    start_time = time.time()

    # Setup the logger
    logging.basicConfig(format='%(asctime)s: %(message)s', level=logging.INFO)

    # Run the parser
    process(args.in_dir, args.out_dir, args.n_jobs)

    # Done!
    logging.info("Done! Took %.2f seconds." % (time.time() - start_time))
