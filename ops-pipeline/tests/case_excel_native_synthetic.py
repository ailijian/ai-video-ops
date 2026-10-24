"""Test-only transports. Real upload acquisition, frame extraction and builders.

No Approval/Type/Publication writer is imported or replaced. Network is disabled.
"""
from pathlib import Path
import argparse,contextlib,json,socket,sys
from case_review_synthetic import SyntheticModels,read,write


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pipeline',type=Path,required=True)
    parser.add_argument('--source-url',required=True);parser.add_argument('--attempt-id',required=True)
    parser.add_argument('--industry',default='待分类');parser.add_argument('--acquisition-provider',default='upload_only')
    parser.add_argument('--source-upload-id',required=True);parser.add_argument('--source-upload-receipt-sha256',required=True)
    args=parser.parse_args();pipeline=args.pipeline.resolve();sys.path.insert(0,str(pipeline/'scripts'))
    from case_analysis_v1 import Orchestrator
    operation=Orchestrator(pipeline_root=pipeline,repo_root=pipeline.parent,downloader_root=pipeline.parent/'douyin-downloader',
        source_url=args.source_url,attempt_id=args.attempt_id,profile=None,industry=args.industry,reanalyze=False,
        source_upload_id=args.source_upload_id,source_upload_receipt_sha256=args.source_upload_receipt_sha256,
        acquisition_provider=args.acquisition_provider)
    model=SyntheticModels();original=operation.run_command
    def transport(label,command,*a,**kw):
        name=Path(command[1]).stem
        def arg(key):return command[command.index(key)+1]
        if name=='transcribe_case':
            video=Path(arg('--input'));folder=Path(arg('--output-root'))/video.stem
            transcript='这是全虚构视频的合成分析口播'
            write(folder/'transcript_segments.json',{'source_file':str(video),'duration':6,'model':'synthetic-ASR-test-only','discarded_segments':[],'segments':[
                {'start':.2,'end':2.5,'text':transcript,'words':[{'start':.2,'end':2.5,'word':transcript,'probability':.99}]}]})
        elif name=='analyze_visual_timeline_v1':
            path=Path(arg('--manifest'));manifest=read(path)
            frames=[{**frame,'frame_id':frame['filename'],'ocr_raw':'全虚构','scene_summary':'合成画面解释','visible_facts':['全虚构色块'],
                'visual_change_from_previous':'画面变化','new_visual_information':['色块变化'],'uncertainties':[]} for frame in manifest['frames']]
            write(path.parent/'visual_v1/visual_timeline_v1.json',{'case_id':operation.case_id,'duration_seconds':6,'frames':frames,
                'coverage':{'coverage_label':'candidate_complete','candidate_frame_count':len(frames),'analyzed_frame_count':len(frames)}})
        elif name=='extract_visual_evidence':
            original(label,command,*a,**kw)  # Real CPU extraction from uploaded media.
        else:
            log=operation.attempt_root/'logs/synthetic-builder-output.log'
            log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('a',encoding='utf8') as stream,contextlib.redirect_stdout(stream):
                model.command(label,command,*a,**kw)
    operation.run_command=transport
    socket.socket.connect=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('No network in fictional Native test'))
    state=operation.run()
    print(json.dumps({'status':state['status'],'case_id':operation.case_id,'attempt_id':operation.attempt_id,'synthetic_model_transports':True}))


def make_media(path,seed=0):
    import av,numpy as np
    with av.open(str(path),'w') as out:
        v=out.add_stream('mpeg4',rate=10);v.width=160;v.height=96;v.pix_fmt='yuv420p'
        a=out.add_stream('aac',rate=48000);a.layout='mono'
        for n in range(60):
            pixels=np.zeros((96,160,3),dtype=np.uint8);pixels[:,:,1]=(80+n*2+seed*7)%256
            frame=av.VideoFrame.from_ndarray(pixels,format='rgb24');frame.pts=n
            for packet in v.encode(frame):out.mux(packet)
        for packet in v.encode():out.mux(packet)
        for n in range(6):
            frame=av.AudioFrame.from_ndarray(np.zeros((1,48000),dtype=np.float32),format='fltp',layout='mono')
            frame.sample_rate=48000;frame.pts=n*48000
            for packet in a.encode(frame):out.mux(packet)
        for packet in a.encode():out.mux(packet)


if __name__=='__main__':
    if len(sys.argv) in {3,4} and sys.argv[1]=='--make-media':make_media(Path(sys.argv[2]),int(sys.argv[3]) if len(sys.argv)==4 else 0)
    else:main()
