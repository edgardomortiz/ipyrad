#!/usr/bin/env python2.7

""" loads an archived Assembly object. """

from __future__ import print_function

import os
import dill
import time
import json
import pandas as pd
import ipyrad as ip
from copy import deepcopy
from ipyrad.assemble.util import *
from collections import OrderedDict

# pylint: disable=W0212
# pylint: disable=W0142

def load_assembly(assemblyname, quiet=False):
    """ loads an ipython dill pickled Assembly object """

    ## flexible name entry
    locations = [assemblyname]
    locations.append(assemblyname+".assembly")

    ## does Assembly saved obj exist?
    for name in locations:
        try:
            ## load in the Assembly object
            with open(name, "rb") as pickin:
                data = dill.load(pickin)

            ## will raise Attribute error if not loaded

            ## create shorter print name if in user path
            name = name.replace(os.path.expanduser("~"), "~")
            
            ## print msg
            if not quiet:
                print("  loading Assembly: {} [{}]".format(data.name, name))

            ## Test if our assembly is currently up to date
            ## How to deal with assembly objects falling out of synch with the 
            ## currently assembly params in the code. If forceupdate is on
            ## then update the loaded assembly to the current version. If 
            ## forceupdate is not on, then test to check if the loaded
            ## assembly is current. If it is then fine, if not bail out with
            ## a hopefully useful error message.
            if test_assembly(data):
                print("  Attempting to update assembly to newest version.")
                data = update_assembly(data)

        except (IOError, AttributeError):
            pass

    try:
        return data
    except UnboundLocalError:
        raise AssertionError("Attempting to load assembly. File not found: {}"\
                             .format(assemblyname))



def test_assembly(data):
    """ Check to see if the assembly you're trying to load is concordant
        with the current assembly version. Basically it creates a new tmp
        assembly and tests whether the paramsdicts are the same. It also
        tests the _hackersonly dict."""

    new_assembly = ip.Assembly(data.name, quiet=True)
    new_params = set(new_assembly.paramsdict.keys())

    my_params = set(data.paramsdict.keys())

    ## Find all params that are in the new paramsdict and not in the old one.
    params_diff = new_params.difference(my_params)

    result = False
    if params_diff:
        result = True

    ## Test hackersonly dict as well.
    my_hackerdict = set(data._hackersonly.keys())
    new_hackerdict = set(new_assembly._hackersonly.keys())
    hackerdict_diff = new_hackerdict.difference(my_hackerdict)

    if hackerdict_diff:
        result = True

    return result



def update_assembly(data):
    """ Create a new Assembly() and convert as many of our old params to the new
        version as we can. Also report out any parameters that are removed
        and what their values are. 
    """

    print("##############################################################")
    print("Updating assembly to current version")
    ## New assembly object to update pdate from.
    new_assembly = ip.Assembly("update", quiet=True)

    ## Hackersonly dict gets automatically overwritten
    ## Always use the current version for params in this dict.
    data._hackersonly = deepcopy(new_assembly._hackersonly)

    new_params = set(new_assembly.paramsdict.keys())

    my_params = set(data.paramsdict.keys())

    ## Find all params in loaded assembly that aren't in the new assembly.
    ## Make a new dict that doesn't include anything in removed_params
    removed_params = my_params.difference(new_params)
    for i in removed_params:
        print("Removing parameter: {} = {}".format(i, data.paramsdict[i]))
        
    ## Find all params that are in the new paramsdict and not in the old one.
    ## If the set isn't emtpy then we create a new dictionary based on the new
    ## assembly parameters and populated with currently loaded assembly values.
    ## Conditioning on not including any removed params. Magic.
    added_params = new_params.difference(my_params)
    for i in added_params:
        print("Adding parameter: {} = {}".format(i, new_assembly.paramsdict[i]))

    print("\nPlease take note of these changes. Every effort is made to\n"\
            +"ensure compatibility across versions of ipyrad. See online\n"\
            +"documentation for further details about new parameters.")
    time.sleep(5)
    print("##############################################################")
    
    if added_params:
        for i in data.paramsdict:
            if i not in removed_params:
                new_assembly.paramsdict[i] = data.paramsdict[i]
        data.paramsdict = deepcopy(new_assembly.paramsdict)

    data.save()
    return data



def save_json(data):
    """ Save assembly and samples as json """

    ## data as dict
    #### skip _ipcluster because it's made new
    #### skip _headers because it's loaded new
    #### statsfiles save only keys
    #### samples save only keys
    datadict = OrderedDict([
        ("_version", data.__dict__["_version"]),
        ("name", data.__dict__["name"]), 
        ("dirs", data.__dict__["dirs"]),
        ("paramsdict", data.__dict__["paramsdict"]),
        ("samples", data.__dict__["samples"].keys()),
        ("populations", data.__dict__["populations"]),
        ("database", data.__dict__["database"]),
        ("outfiles", data.__dict__["outfiles"]),
        ("barcodes", data.__dict__["barcodes"]),
        ])

    ## sample dict
    sampledict = OrderedDict([])
    for key, sample in data.samples.iteritems():
        sampledict[key] = sample._to_fulldict()

    ## json format it
    fulldump = json.dumps({
        "assembly": datadict,
        "samples": sampledict
        },
        sort_keys=False, indent=4, separators=(",", ":")
        )

    ## save to file
    assemblypath = os.path.join(data.dirs.project, data.name+".json")
    
    ## protect save from interruption
    done = 0
    while not done:
        try:
            with open(assemblypath, 'w') as jout:
                jout.write(fulldump)
            done = 1
        except (KeyboardInterrupt, SystemExit): 
            print('.')
            continue



def load_json(path, quiet=False):
    """ Load a json serialized object and ensure it matches to the current 
    Assembly object format """

    ## load the JSON string and try with name+.json
    checkfor = [path, path+".json"]
    for inpath in checkfor:
        try:
            with open(inpath, 'r') as infile:
                fullj = json.loads(infile.read(),
                        object_pairs_hook=OrderedDict)
        except IOError:
            pass

    ## create a new empty Assembly
    try:
        oldname = fullj["assembly"].pop("name")
        olddir = fullj["assembly"]["dirs"]["project"]
        oldpath = os.path.join(olddir, os.path.splitext(oldname)[0]+".json")
        null = ip.Assembly(oldname, quiet=True)

    except AttributeError as inst:
        raise IPyradWarningExit("""
    Could not find saved Assembly file (.json) in path: {}
    Expected location is: [project_dir]/[assembly_name]
    """.format(inpath))

    ## print msg with shortpath
    if not quiet:
        oldpath = oldpath.replace(os.path.expanduser("~"), "~")
        print("  loading Assembly: {} [{}]".format(oldname, oldpath))

    ## First get the samples. Create empty sample dict of correct length 
    samplekeys = fullj["assembly"].pop("samples")
    null.samples = {name: "" for name in samplekeys}

    ## Next get paramsdict and use set_params to convert values back to 
    ## the correct dtypes
    oldparams = fullj["assembly"].pop("paramsdict")
    for param, val in oldparams.iteritems():
        if param != "assembly_name":
            null.set_params(param, val)

    ## Check remaining attributes of Assembly and Raise warning if attributes
    ## do not match up between old and new objects
    newkeys = null.__dict__.keys()
    oldkeys = fullj["assembly"].keys()
    ## find shared keys and deprecated keys
    sharedkeys = set(oldkeys).intersection(set(newkeys))
    lostkeys = set(oldkeys).difference(set(newkeys))

    ## raise warning if there are lost/deprecated keys
    if lostkeys:
        LOGGER.error("""
    :: load_json found {a} keys that are unique to the older Assembly.
        - assembly [{b}] v.[{c}] has: {d}
        - current assembly is v.[{e}]
        """.format(a=len(lostkeys), 
                   b=oldname,
                   c=fullj["assembly"]["_version"],
                   d=lostkeys,
                   e=null._version))

    ## load in remaining shared Assembly attributes to null
    for key in sharedkeys:
        null.__setattr__(key, fullj["assembly"][key])

    ## Now, load in the Sample objects json dicts
    sample_names = fullj["samples"].keys()
    sample_keys = fullj["samples"][sample_names[0]].keys()
    stats_keys = fullj["samples"][sample_names[0]]["stats"].keys()
    statsfiles_keys = fullj["samples"][sample_names[0]]["statsfiles"].keys()
    ind_statkeys = \
        [fullj["samples"][sample_names[0]]["statsfiles"][i].keys() \
        for i in statsfiles_keys]
    ind_statkeys = list(itertools.chain(*ind_statkeys))

    ## check against a null sample
    nsamp = ip.Sample()
    newkeys = nsamp.__dict__.keys()
    newstats = nsamp.__dict__["stats"].keys()
    newstatfiles = nsamp.__dict__["statsfiles"].keys()
    newindstats = [nsamp.__dict__["statsfiles"][i].keys() for i in newstatfiles]
    newindstats = list(itertools.chain(*[i.values for i in newindstats]))

    ## different in attributes?
    diffattr = set(sample_keys).difference(newkeys)
    diffstats = set(stats_keys).difference(newstats)
    diffindstats = set(ind_statkeys).difference(newindstats)

    ## Raise warning if any oldstats were lost or deprecated
    alldiffs = diffattr.union(diffstats).union(diffindstats)
    if any(alldiffs):
        LOGGER.error("""
    :: load_json found {a} keys that are unique to the older Samples.
        - assembly [{b}] v.[{c}] has: {d}
        - current assembly is v.[{e}]
        """.format(a=len(alldiffs), 
                   b=oldname,
                   c=fullj["assembly"]["_version"],
                   d=alldiffs,
                   e=null._version))

    ## save stats and statsfiles to Samples
    for sample in null.samples:
        ## create a null Sample
        null.samples[sample] = ip.Sample()
        ## set ObjDicts
        null.samples[sample].statsfiles = ObjDict()
        null.samples[sample].files = ObjDict()        

        ## save stats
        sdat = fullj["samples"][sample]['stats']
        null.samples[sample].stats = pd.Series(sdat)

        ## save statsfiles
        for statskey in statsfiles_keys:
            null.samples[sample].statsfiles[statskey] = \
                pd.Series(fullj["samples"][sample]["statsfiles"][statskey])

    ## save to assembly object
    for statskey in statsfiles_keys:
        indstat = null.build_stat(statskey)
        if not indstat.empty:
            null.statsfiles[statskey] = indstat

    ## add remaning attributes to null Samples
    shared_keys = set(sample_keys).intersection(newkeys)
    shared_keys.discard("stats")
    shared_keys.discard("statsfiles")

    for sample in null.samples:
        ## set the others
        for key in shared_keys:
            null.samples[sample].__setattr__(key, fullj["samples"][sample][key])

    ## make back into object dicts
    null.dirs = ObjDict(null.dirs)
    null.statsfiles = ObjDict(null.statsfiles)
    null.populations = ObjDict(null.populations)
    null.outfiles = ObjDict(null.outfiles)

    return null


