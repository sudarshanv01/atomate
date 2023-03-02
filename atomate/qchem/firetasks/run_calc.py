# This module defines tasks that support running QChem in various ways.


import os
import shutil
import subprocess

import numpy as np
from custodian import Custodian
from custodian.qchem.handlers import QChemErrorHandler
from custodian.qchem.jobs import QCJob
from fireworks import FiretaskBase, explicit_serialize
from pymatgen.io.qchem.inputs import QCInput

from atomate.utils.utils import env_chk, get_logger

__author__ = "Samuel Blau, Evan Spotte-Smith"
__copyright__ = "Copyright 2018, The Materials Project"
__version__ = "0.1"
__maintainer__ = "Samuel Blau"
__email__ = "samblau1@gmail.com"
__status__ = "Alpha"
__date__ = "5/11/18"
__credits__ = "Shyam Dwaraknath, Xiaohui Qu, Shyue Ping Ong, Anubhav Jain"

logger = get_logger(__name__)


@explicit_serialize
class RunQChemDirect(FiretaskBase):
    """
    Execute a command directly (no custodian).

    Required params:
        qchem_cmd (str): The name of the full command line call to run. This should include any
                         flags for parallelization, saving scratch, and input / output files.
                         Does NOT support env_chk.
    """

    required_params = ["qchem_cmd"]

    def run_task(self, fw_spec):
        cmd = self.get("qchem_cmd")
        os.putenv("QCSCRATCH", os.getcwd())

        logger.info(f"Running command: {cmd}")
        return_code = subprocess.call(cmd, shell=True)
        logger.info(f"Command {cmd} finished running with return code: {return_code}")


@explicit_serialize
class RunQChemCustodian(FiretaskBase):
    """
    Run QChem using custodian "on rails", i.e. in a simple way that supports most common options.

    Required params:
        qchem_cmd (str): The name of the full executable for running QChem. Note that this is
                         explicitly different from qchem_cmd in RunQChemDirect because it does
                         not include any flags and should only be the call to the executable.
                         Supports env_chk.

    Optional params:
        multimode (str): Parallelization scheme, either openmp or mpi. Defaults to openmp.
                         Supports env_chk.
        input_file (str): Name of the QChem input file. Defaults to "mol.qin".
        output_file (str): Name of the QChem output file. Defaults to "mol.qout"
        max_cores (int): Maximum number of cores to parallelize over. Supports env_chk.
        qclog_file (str): Name of the file to redirect the standard output to. None means
                          not to record the standard output. Defaults to None.
        suffix (str): String to append to the file in postprocess.
        calc_loc (str): Path where Q-Chem should run. Will env_chk by default. If not in
                        environment, will be set to None, in which case Q-Chem will run in
                        the system-defined QCLOCALSCR.
        nboexe (str): Path to the NBO7 executable.
        save_scratch (bool): Whether to save scratch directory contents. Defaults to False.
        max_errors (int): Maximum # of errors to fix before giving up (default=5)
        job_type (str): Choose from "normal" (default) and "opt_with_frequency_flattener"
        handler_group (str): Group of handlers to use. See handler_groups dict in the code
                             for the groups and complete list of handlers in each group.
        gzip_output (bool): gzip output, defaults to True.
        backup (bool): Whether to backup the initial input file. If True, the input will
                       be copied with a ".orig" appended. Defaults to True.

        *** Just for opt_with_frequency_flattener ***
        linked (bool): Whether or not to use the linked flattener. Defaults to True.
        max_iterations (int): Number of perturbation -> optimization -> frequency iterations
                              to perform. Defaults to 10.
        max_molecule_perturb_scale (float): The maximum scaled perturbation that can be
                                            applied to the molecule. Defaults to 0.3.

    """

    required_params = ["qchem_cmd"]
    optional_params = [
        "multimode",
        "input_file",
        "output_file",
        "max_cores",
        "qclog_file",
        "suffix",
        "calc_loc",
        "nboexe",
        "save_scratch",
        "max_errors",
        "job_type",
        "handler_group",
        "gzipped_output",
        "backup",
        "linked",
        "max_iterations",
        "max_molecule_perturb_scale",
        "freq_before_opt",
        "transition_state",
    ]

    def run_task(self, fw_spec):

        # initialize variables
        qchem_cmd = env_chk(self["qchem_cmd"], fw_spec)
        multimode = env_chk(self.get("multimode"), fw_spec)
        if multimode is None:
            multimode = "openmp"
        """
        Note that I'm considering hardcoding openmp in the future
        because there is basically no reason anyone should ever run
        QChem on multiple nodes, aka with multimode = mpi.
        """
        input_file = self.get("input_file", "mol.qin")
        output_file = self.get("output_file", "mol.qout")
        max_cores = env_chk(self["max_cores"], fw_spec)
        qclog_file = self.get("qclog_file", "mol.qclog")
        suffix = self.get("suffix", "")
        calc_loc = self.get("calc_loc", env_chk(">>calc_loc<<", fw_spec, strict=False))
        nboexe = self.get("nboexe", env_chk(">>nboexe<<", fw_spec, strict=False))
        save_scratch = self.get("save_scratch", False)
        max_errors = self.get("max_errors", 5)
        max_iterations = self.get("max_iterations", 10)
        linked = self.get("linked", True)
        backup = self.get("backup", True)
        max_molecule_perturb_scale = self.get("max_molecule_perturb_scale", 0.3)
        job_type = self.get("job_type", "normal")
        gzipped_output = self.get("gzipped_output", True)
        transition_state = self.get("transition_state", False)
        freq_before_opt = self.get("freq_before_opt", False)

        handler_groups = {
            "default": [
                QChemErrorHandler(input_file=input_file, output_file=output_file)
            ],
            "no_handler": [],
        }

        # construct jobs
        if job_type == "normal":
            jobs = [
                QCJob(
                    qchem_command=qchem_cmd,
                    max_cores=max_cores,
                    multimode=multimode,
                    input_file=input_file,
                    output_file=output_file,
                    qclog_file=qclog_file,
                    suffix=suffix,
                    calc_loc=calc_loc,
                    nboexe=nboexe,
                    save_scratch=save_scratch,
                    backup=backup,
                )
            ]
        elif job_type == "opt_with_frequency_flattener":
            if linked:
                jobs = QCJob.opt_with_frequency_flattener(
                    qchem_command=qchem_cmd,
                    multimode=multimode,
                    input_file=input_file,
                    output_file=output_file,
                    qclog_file=qclog_file,
                    max_iterations=max_iterations,
                    linked=linked,
                    freq_before_opt=freq_before_opt,
                    transition_state=transition_state,
                    save_final_scratch=save_scratch,
                    max_cores=max_cores,
                    calc_loc=calc_loc,
                    nboexe=nboexe,
                )
            else:
                jobs = QCJob.opt_with_frequency_flattener(
                    qchem_command=qchem_cmd,
                    multimode=multimode,
                    input_file=input_file,
                    output_file=output_file,
                    qclog_file=qclog_file,
                    max_iterations=max_iterations,
                    max_molecule_perturb_scale=max_molecule_perturb_scale,
                    linked=linked,
                    freq_before_opt=freq_before_opt,
                    transition_state=transition_state,
                    save_final_scratch=save_scratch,
                    max_cores=max_cores,
                    calc_loc=calc_loc,
                    nboexe=nboexe,
                )

        else:
            raise ValueError(f"Unsupported job type: {job_type}")

        # construct handlers
        handlers = handler_groups[self.get("handler_group", "default")]

        c = Custodian(
            handlers, jobs, max_errors=max_errors, gzipped_output=gzipped_output
        )

        c.run()


@explicit_serialize
class RunNoQChem(FiretaskBase):
    """
    Do NOT run QChem. Do nothing.
    """

    def run_task(self, fw_spec):
        pass


@explicit_serialize
class RunQChemFake(FiretaskBase):
    """
    QChem Emulator

    Required params:
        ref_dir (string): Path to reference qchem run directory with input file in the folder
           named "mol.qin" and output file in the folder named "mol.qout".

    """

    required_params = ["ref_dir"]
    optional_params = ["input_file"]

    def run_task(self, fw_spec):
        self._verify_inputs()
        self._clear_inputs()
        self._generate_outputs()

    def _verify_inputs(self):
        input_file = self.get("input_file", "mol.qin")
        user_qin = QCInput.from_file(os.path.join(os.getcwd(), "mol.qin"))

        # Check mol.qin
        ref_qin = QCInput.from_file(os.path.join(self["ref_dir"], input_file))

        np.testing.assert_equal(ref_qin.molecule.species, user_qin.molecule.species)
        np.testing.assert_allclose(
            ref_qin.molecule.cart_coords, user_qin.molecule.cart_coords, atol=0.0001
        )
        for key in ref_qin.rem:
            if user_qin.rem.get(key) != ref_qin.rem.get(key):
                raise ValueError(f"Rem key {key} is inconsistent!")
        if ref_qin.opt is not None:
            for key in ref_qin.opt:
                if user_qin.opt.get(key) != ref_qin.opt.get(key):
                    raise ValueError(f"Opt key {key} is inconsistent!")
        if ref_qin.pcm is not None:
            for key in ref_qin.pcm:
                if user_qin.pcm.get(key) != ref_qin.pcm.get(key):
                    raise ValueError(f"PCM key {key} is inconsistent!")
        if ref_qin.solvent is not None:
            for key in ref_qin.solvent:
                if user_qin.solvent.get(key) != ref_qin.solvent.get(key):
                    raise ValueError(f"Solvent key {key} is inconsistent!")

        logger.info("RunQChemFake: verified input successfully")

    @staticmethod
    def _clear_inputs():
        p = os.path.join(os.getcwd(), "mol.qin")
        if os.path.exists(p):
            os.remove(p)

    def _generate_outputs(self):
        # pretend to have run QChem by copying pre-generated output from reference dir to cur dir
        for file_name in os.listdir(self["ref_dir"]):
            full_file_name = os.path.join(self["ref_dir"], file_name)
            if os.path.isfile(full_file_name):
                shutil.copy(full_file_name, os.getcwd())
        logger.info("RunQChemFake: ran fake QChem, generated outputs")
