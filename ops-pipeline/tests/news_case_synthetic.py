"""Only fictional acquisition/ASR/vision/model boundary, never Approval/Gates."""
from pathlib import Path
from unittest.mock import patch
import sys,socket
import case_review_synthetic as base


class NewsModels(base.SyntheticModels):
    def __init__(self,**kwargs):super().__init__(**kwargs,cut_indexes={0,1,3,4})
    def command(self,label,command,*args,**kwargs):
        name=Path(command[1]).stem
        def arg(key):return Path(command[command.index(key)+1])
        if name=='build_privacy_projection_v1':
            # External ASR/Qwen outputs are explicitly fictional; all native
            # privacy, boundary, storyboard, Case and Human writers run below.
            audio=base.read(arg('--audio-v1'));audio['transcript_raw']='虚构演示'
            audio['segments'][0].update(start=.2,end=.4,source_text='虚构演示')
            audio['words'][0].update(start=.2,end=.4,midpoint=.3,text='虚构演示')
            base.write(arg('--audio-v1'),audio)
            visual=base.read(arg('--visual-v1'));number=int(str(visual['case_id'])[-1])
            values=[(f'虚构套餐{number*10+19}元',f'虚构套餐与价格牌{number}'),
                ('含一份主食',f'虚构主食餐盘{number}'),('含一份主食',f'虚构主食餐盘{number}'),
                ('当次确认菜品',f'虚构菜单与订单{number}'),('到店取餐',f'虚构取餐台{number}'),('到店取餐',f'虚构取餐台{number}')]
            for frame,(text,scene) in zip(visual['frames'],values):
                frame.update(ocr_raw=text,scene_summary=scene,visible_facts=[scene],new_visual_information=[text])
            base.write(arg('--visual-v1'),visual)
        if name=='generate_reverse_storyboard':command=[*command,'--source-profile','news']
        return super().command(label,command,*args,**kwargs)


if __name__=='__main__':
    socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Synthetic News Case: external network forbidden'))
    root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root/'scripts'))
    with patch.object(base,'SyntheticModels',NewsModels):
        base.prepare(root,sys.argv[2],sys.argv[3])
