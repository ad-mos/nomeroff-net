import os
import sys
from typing import List, Dict, Tuple
import numpy as np

import torch
import pytorch_lightning as pl
from pytorch_lightning.callbacks import ModelCheckpoint

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'base')))
from .tools import (modelhub,
                    get_mode_torch)
from data_modules.numberplate_orientation_data_module import OrientationDataModule, show_data
from nnmodels.numberplate_orientation_model import NPOrientationNet
from data_modules.data_loaders import normalize
from .OptionsDetector import OptionsDetector


mode_torch = get_mode_torch()


class OrientationDetector(object):
    """
    TODO: describe class
    """
    def __init__(self, orientations: List = None) -> None:
        """
        TODO: describe __init__
        """
        super().__init__()

        if orientations is None:
            self.orientations = [
                0, 
                90, 
                180, 
                270
            ]

        # input
        self.height = 300
        self.width = 300
        self.color_channels = 3

        self.orientations = orientations

        # model
        self.model = None
        self.trainer = None

        # data module
        self.dm = None

        # train hyperparameters
        self.batch_size = 64
        self.epochs = 100
        self.gpus = 1

    @classmethod
    def get_classname(cls: object) -> str:
        return cls.__name__

    def create_model(self) -> NPOrientationNet:
        """
        TODO: describe method
        """
        self.model = NPOrientationNet(len(self.orientations),
                                      self.height,
                                      self.width,
                                      self.batch_size)
        if mode_torch == "gpu":
            self.model = self.model.cuda()
        return self.model

    def prepare(self,
                base_dir: str,
                train_json_path=None,
                validation_json_path=None,
                num_workers=0,
                verbose=False) -> None:
        """
        TODO: describe method
        """
        train_dir = os.path.join(base_dir, 'train')
        if train_json_path is None:
            train_json_path = os.path.join(base_dir, 'train/via_region_data_orientation.json')
        validation_dir = os.path.join(base_dir, 'val')
        if validation_json_path is None:
            validation_json_path = os.path.join(base_dir, 'val/via_region_data_orientation.json')
        
        if verbose:
            show_data(validation_dir, validation_json_path)
            
        # compile generators
        self.dm = OrientationDataModule(
            train_dir,
            train_json_path,
            validation_dir,
            validation_json_path,
            width=self.width,
            height=self.height,
            angles=self.orientations,
            num_workers=num_workers,
            batch_size=self.batch_size)

    def load_model(self, path_to_model):
        if mode_torch == "gpu":
            self.model = NPOrientationNet.load_from_checkpoint(path_to_model,
                                                               orientation_output_size=len(self.orientations))
        else:
            self.model = NPOrientationNet.load_from_checkpoint(path_to_model,
                                                               map_location=torch.device('cpu'),
                                                               orientation_output_size=len(self.orientations))
        self.model.eval()
        return self.model
    
    def test(self) -> List:
        """
        TODO: describe method
        """
        return self.trainer.test()

    def save(self, path: str, verbose: bool = True) -> None:
        """
        TODO: describe method
        """
        if self.model is not None:
            if bool(verbose):
                print("model save to {}".format(path))
            self.trainer.save_checkpoint(path)

    def load(self, path_to_model: str = "latest", options: Dict = None) -> NPOrientationNet:
        """
        TODO: describe method
        """
        if options is None:
            options = dict()
        self.create_model()
        if path_to_model == "latest":
            model_info = modelhub.download_model_by_name("numberplate_orientation")
            path_to_model = model_info["path"]
            options["orientations"] = model_info["orientations"]
        elif path_to_model.startswith("http"):
            model_info = modelhub.download_model_by_url(path_to_model, self.get_classname(), "numberplate_orientation")
            path_to_model = model_info["path"]

        return self.load_model(path_to_model)
    
    def train(self,
              log_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), 
                                                   '../data/logs/options'))
              ) -> NPOrientationNet:
        """
        TODO: describe method
        TODO: add ReduceLROnPlateau callback
        """
        self.create_model()
        checkpoint_callback = ModelCheckpoint(dirpath=log_dir, monitor='val_loss')
        self.trainer = pl.Trainer(max_epochs=self.epochs,
                                  gpus=self.gpus,
                                  callbacks=[checkpoint_callback])
        self.trainer.fit(self.model, self.dm)
        print("[INFO] best model path", checkpoint_callback.best_model_path)
        self.trainer.test()
        return self.model
    
    def tune(self) -> NPOrientationNet:
        """
        TODO: describe method
        TODO: add ReduceLROnPlateau callback
        """
        model = self.create_model()
        trainer = pl.Trainer(auto_lr_find=True,
                             max_epochs=self.epochs,
                             gpus=self.gpus)
        return trainer.tune(model, self.dm)
    
    def predict(self, imgs: List[np.ndarray], return_acc=False) -> Tuple:
        """
        TODO: describe method
        """
        orientations, confidences, predicted = self.predict_with_confidence(imgs)
        if return_acc:
            return orientations, predicted
        return orientations

    @torch.no_grad()
    def predict_with_confidence(self, imgs: List[np.ndarray]) -> Tuple:
        """
        TODO: describe method
        """
        xs = []
        for img in imgs:
            xs.append(normalize(img))

        predicted = [[], []]
        if bool(xs):
            x = torch.tensor(np.moveaxis(np.array(xs), 3, 1))
            if mode_torch == "gpu":
                x = x.cuda()
            predicted = self.model(x)
            predicted = [p.cpu().numpy() for p in predicted]

        confidences = []
        orientations = []
        for orientation in predicted:
            orientations.append(int(np.argmax(orientation)))
            orientation = orientation.tolist()
            orientation_confidence = orientation[int(np.argmax(orientation))]
            confidences.append(orientation_confidence)
        return orientations, confidences, predicted

    def get_orientations(self, index: int) -> int:
        """
        TODO: describe method
        """
        return self.orientations[index]